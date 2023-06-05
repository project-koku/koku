#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Asynchronous tasks."""
import json
import logging
import os
from collections import defaultdict
from decimal import Decimal
from decimal import InvalidOperation

import ciso8601
import pandas as pd
from celery import chain
from celery import group
from dateutil import parser
from django.conf import settings
from django.db import connection
from django.db.utils import IntegrityError
from django_tenants.utils import schema_context

import masu.prometheus_stats as worker_stats
from api.common import log_json
from api.iam.models import Tenant
from api.provider.models import Provider
from api.utils import DateHelper
from api.utils import get_months_in_date_range
from koku import celery_app
from koku.middleware import KokuTenantMiddleware
from masu.config import Config
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ingress_report_db_accessor import IngressReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.exceptions import MasuProcessingError
from masu.exceptions import MasuProviderError
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
from masu.external.report_downloader import ReportDownloaderError
from masu.processor import is_customer_large
from masu.processor import is_ocp_on_cloud_summary_disabled
from masu.processor import is_source_disabled
from masu.processor import is_summary_processing_disabled
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor._tasks.remove_expired import _remove_expired_data
from masu.processor.cost_model_cost_updater import CostModelCostUpdater
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import DELETE_TABLE
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import TRUNCATE_TABLE
from masu.processor.parquet.ocp_cloud_parquet_report_processor import OCPCloudParquetReportProcessor
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError
from masu.processor.report_summary_updater import ReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdaterCloudError
from masu.processor.report_summary_updater import ReportSummaryUpdaterProviderNotFoundError
from masu.processor.worker_cache import rate_limit_tasks
from masu.processor.worker_cache import WorkerCache
from masu.util.aws.common import remove_files_not_in_set_from_s3_bucket
from masu.util.common import execute_trino_query
from masu.util.common import get_path_prefix
from masu.util.gcp.common import deduplicate_reports_for_gcp
from masu.util.oci.common import deduplicate_reports_for_oci


LOG = logging.getLogger(__name__)

DEFAULT = "celery"
GET_REPORT_FILES_QUEUE = "download"
OCP_QUEUE = "ocp"
PRIORITY_QUEUE = "priority"
MARK_MANIFEST_COMPLETE_QUEUE = "priority"
REMOVE_EXPIRED_DATA_QUEUE = "summary"
SUMMARIZE_REPORTS_QUEUE = "summary"
UPDATE_COST_MODEL_COSTS_QUEUE = "cost_model"
UPDATE_SUMMARY_TABLES_QUEUE = "summary"
DELETE_TRUNCATE_QUEUE = "refresh"

# any additional queues should be added to this list
QUEUE_LIST = [
    DEFAULT,
    GET_REPORT_FILES_QUEUE,
    OCP_QUEUE,
    PRIORITY_QUEUE,
    MARK_MANIFEST_COMPLETE_QUEUE,
    REMOVE_EXPIRED_DATA_QUEUE,
    SUMMARIZE_REPORTS_QUEUE,
    UPDATE_COST_MODEL_COSTS_QUEUE,
    UPDATE_SUMMARY_TABLES_QUEUE,
]


def record_all_manifest_files(manifest_id, report_files, tracing_id):
    """Store all report file names for manifest ID."""
    for report in report_files:
        try:
            with ReportStatsDBAccessor(report, manifest_id):
                LOG.debug(log_json(tracing_id, msg=f"Logging {report} for manifest ID: {manifest_id}"))
        except IntegrityError:
            # OCP records the entire file list for a new manifest when the listener
            # recieves a payload.  With multiple listeners it is possilbe for
            # two listeners to recieve a report file for the same manifest at
            # roughly the same time.  In that case the report file may already
            # exist and an IntegrityError would be thrown.
            LOG.debug(log_json(tracing_id, msg=f"Report {report} has already been recorded."))


def record_report_status(manifest_id, file_name, tracing_id, context={}):
    """
    Creates initial report status database entry for new report files.

    If a report has already been downloaded from the ingress service
    there is a chance that processing has already been complete.  The
    function returns the last completed date time to determine if the
    report processing should continue in extract_payload.

    Args:
        manifest_id (Integer): Manifest Identifier.
        file_name (String): Report file name
        tracing_id (String): Identifier associated with the payload
        context (Dict): Context for logging (account, etc)

    Returns:
        DateTime - Last completed date time for a given report file.

    """
    already_processed = False
    with ReportStatsDBAccessor(file_name, manifest_id) as db_accessor:
        already_processed = db_accessor.get_last_completed_datetime()
        if already_processed:
            msg = f"Report {file_name} has already been processed."
        else:
            msg = f"Recording stats entry for {file_name}"
        LOG.info(log_json(tracing_id, msg=msg, context=context))
    return already_processed


@celery_app.task(name="masu.processor.tasks.get_report_files", queue=GET_REPORT_FILES_QUEUE, bind=True)  # noqa: C901
def get_report_files(  # noqa: C901
    self,
    customer_name,
    authentication,
    billing_source,
    provider_type,
    schema_name,
    provider_uuid,
    report_month,
    report_context,
    tracing_id,
    ingress_reports=None,
    ingress_reports_uuid=None,
):
    """
    Task to download a Report and process the report.

    FIXME: A 2 hour timeout is arbitrarily set for in progress processing requests.
    Once we know a realistic processing time for the largest CUR file in production
    this value can be adjusted or made configurable.

    Args:
        customer_name     (String): Name of the customer owning the cost usage report.
        authentication    (String): Credential needed to access cost usage report
                                    in the backend provider.
        billing_source    (String): Location of the cost usage report in the backend provider.
        provider_type     (String): Koku defined provider type string.  Example: Amazon = 'AWS'
        schema_name       (String): Name of the DB schema

    Returns:
        None

    """
    # Existing schema will start with acct and we strip that prefix for use later
    # new customers include the org prefix in case an org-id and an account number might overlap
    context = {"schema": customer_name}
    if customer_name.startswith("acct"):
        context["account"] = customer_name[4:]
    else:
        context["org_id"] = customer_name[3:]
    context["provider_uuid"] = provider_uuid
    context["provider_type"] = provider_type
    try:
        worker_stats.GET_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()
        month = report_month
        if isinstance(report_month, str):
            month = parser.parse(report_month)
        report_file = report_context.get("key")
        cache_key = f"{provider_uuid}:{report_file}"
        WorkerCache().add_task_to_cache(cache_key)

        try:
            report_dict = _get_report_files(
                tracing_id,
                customer_name,
                authentication,
                billing_source,
                provider_type,
                provider_uuid,
                month,
                report_context,
                ingress_reports,
            )
        except (MasuProcessingError, MasuProviderError, ReportDownloaderError) as err:
            worker_stats.REPORT_FILE_DOWNLOAD_ERROR_COUNTER.labels(provider_type=provider_type).inc()
            WorkerCache().remove_task_from_cache(cache_key)
            LOG.warning(log_json(tracing_id, msg=str(err), context=context), exc_info=err)
            return

        if report_dict:
            context["file"] = report_dict["file"]
            context["invoice_month"] = report_dict.get("invoice_month")
            LOG.info(log_json(tracing_id, msg="reports to be processed", context=context))
        else:
            WorkerCache().remove_task_from_cache(cache_key)
            LOG.info(log_json(tracing_id, msg="no report to be processed", context=context))
            return

        report_meta = {
            "schema_name": schema_name,
            "provider_type": provider_type,
            "provider_uuid": provider_uuid,
            "manifest_id": report_dict.get("manifest_id"),
            "tracing_id": tracing_id,
            "start": report_dict.get("start"),
            "end": report_dict.get("end"),
            "invoice_month": report_dict.get("invoice_month"),
        }

        try:
            LOG.info(log_json(tracing_id, msg="processing starting", context=context))
            worker_stats.PROCESS_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()

            report_dict["tracing_id"] = tracing_id
            report_dict["provider_type"] = provider_type

            result = _process_report_file(
                schema_name, provider_type, report_dict, ingress_reports, ingress_reports_uuid
            )

        except (ReportProcessorError, ReportProcessorDBError) as processing_error:
            worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
            LOG.error(log_json(tracing_id, msg=f"Report processing error: {processing_error}", context=context))
            WorkerCache().remove_task_from_cache(cache_key)
            raise processing_error
        except NotImplementedError as err:
            LOG.info(log_json(tracing_id, msg=f"Not implemented error: {err}", context=context))
            WorkerCache().remove_task_from_cache(cache_key)

        WorkerCache().remove_task_from_cache(cache_key)
        if not result:
            LOG.info(log_json(tracing_id, msg="no report files processed, skipping summary", context=context))
            return None

        return report_meta
    except ReportDownloaderWarning as err:
        LOG.warning(log_json(tracing_id, msg=f"Report downloader Warning: {err}", context=context), exc_info=err)
        WorkerCache().remove_task_from_cache(cache_key)
    except Exception as err:
        worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
        LOG.error(log_json(tracing_id, msg=f"Unknown downloader exception: {err}", context=context), exc_info=err)
        WorkerCache().remove_task_from_cache(cache_key)


@celery_app.task(name="masu.processor.tasks.remove_expired_data", queue=DEFAULT)
def remove_expired_data(schema_name, provider, simulate, provider_uuid=None, queue_name=None):
    """
    Remove expired report data.

    Args:
        schema_name (String) db schema name
        provider    (String) provider type
        simulate    (Boolean) Simulate report data removal

    Returns:
        None

    """
    context = {
        "schema": schema_name,
        "provider_type": provider,
        "provider_uuid": provider_uuid,
    }
    LOG.info(log_json("remove_expired_data", msg="removing expired data", context=context))
    _remove_expired_data(schema_name, provider, simulate, provider_uuid)


@celery_app.task(name="masu.processor.tasks.summarize_reports", queue=SUMMARIZE_REPORTS_QUEUE)
def summarize_reports(reports_to_summarize, queue_name=None, manifest_list=None, ingress_report_uuid=None):
    """
    Summarize reports returned from line summary task.

    Args:
        reports_to_summarize (list) list of reports to process

    Returns:
        None

    """
    reports_by_source = defaultdict(list)
    for report in reports_to_summarize:
        if report:
            reports_by_source[report.get("provider_uuid")].append(report)

    reports_deduplicated = []
    dedup_func_map = {
        Provider.PROVIDER_GCP: deduplicate_reports_for_gcp,
        Provider.PROVIDER_GCP_LOCAL: deduplicate_reports_for_gcp,
        Provider.PROVIDER_OCI: deduplicate_reports_for_oci,
        Provider.PROVIDER_OCI_LOCAL: deduplicate_reports_for_oci,
    }
    LOG.info(log_json("summarize_reports", msg="deduplicating reports"))
    for report_list in reports_by_source.values():
        if report and report.get("provider_type") in dedup_func_map:
            provider_type = report.get("provider_type")
            manifest_list = [] if "oci" in provider_type.lower() else manifest_list
            dedup_func = dedup_func_map.get(provider_type)
            reports_deduplicated.extend(dedup_func(report_list))
        else:
            starts = []
            ends = []
            for report in report_list:
                if report.get("start") and report.get("end"):
                    starts.append(report.get("start"))
                    ends.append(report.get("end"))
                start = min(starts) if starts != [] else None
                end = max(ends) if ends != [] else None
            reports_deduplicated.append(
                {
                    "manifest_id": report.get("manifest_id"),
                    "tracing_id": report.get("tracing_id"),
                    "schema_name": report.get("schema_name"),
                    "provider_type": report.get("provider_type"),
                    "provider_uuid": report.get("provider_uuid"),
                    "start": start,
                    "end": end,
                }
            )

    LOG.info(log_json("summarize_reports", msg=f"deduplicated reports, num report: {len(reports_deduplicated)}"))
    for report in reports_deduplicated:
        # For day-to-day summarization we choose a small window to
        # cover new data from a window of days.
        # This saves us from re-summarizing unchanged data and cuts down
        # on processing time. There are override mechanisms in the
        # Updater classes for when full-month summarization is
        # required.
        with ReportManifestDBAccessor() as manifest_accesor:
            tracing_id = report.get("tracing_id", report.get("manifest_uuid", "no-tracing-id"))

            if not manifest_accesor.manifest_ready_for_summary(report.get("manifest_id")):
                LOG.info(log_json(tracing_id, msg="manifest not ready for summary", context=report))
                continue

            LOG.info(log_json(tracing_id, msg="report to summarize", context=report))

            months = get_months_in_date_range(report)
            for month in months:
                update_summary_tables.s(
                    report.get("schema_name"),
                    report.get("provider_type"),
                    report.get("provider_uuid"),
                    start_date=month[0],
                    end_date=month[1],
                    ingress_report_uuid=ingress_report_uuid,
                    manifest_id=report.get("manifest_id"),
                    queue_name=queue_name,
                    tracing_id=tracing_id,
                    manifest_list=manifest_list,
                    invoice_month=month[2],
                ).apply_async(queue=queue_name or UPDATE_SUMMARY_TABLES_QUEUE)


@celery_app.task(name="masu.processor.tasks.update_summary_tables", queue=UPDATE_SUMMARY_TABLES_QUEUE)  # noqa: C901
def update_summary_tables(  # noqa: C901
    schema,
    provider_type,
    provider_uuid,
    start_date,
    end_date=None,
    manifest_id=None,
    ingress_report_uuid=None,
    queue_name=None,
    synchronous=False,
    tracing_id=None,
    ocp_on_cloud=True,
    manifest_list=None,
    invoice_month=None,
):
    """Populate the summary tables for reporting.

    Args:
        schema_name (str) The DB schema name.
        provider    (str) The provider type.
        provider_uuid (str) The provider uuid.
        report_dict (dict) The report data dict from previous task.
        start_date  (str) The date to start populating the table.
        end_date    (str) The date to end on.

    Returns
        None

    """
    context = {
        "schema": schema,
        "provider_type": provider_type,
        "provider_uuid": provider_uuid,
        "manifest_id": manifest_id,
    }
    if is_summary_processing_disabled(schema):
        LOG.info(f"Summary disabled for {schema}.")
        return
    if is_source_disabled(provider_uuid):
        return
    if is_ocp_on_cloud_summary_disabled(schema):
        LOG.info(f"OCP on Cloud summary disabled for {schema}.")
        ocp_on_cloud = False

    worker_stats.REPORT_SUMMARY_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()
    task_name = "masu.processor.tasks.update_summary_tables"
    if isinstance(start_date, str):
        cache_arg_date = start_date[:-3]  # Strip days from string
    else:
        cache_arg_date = start_date.strftime("%Y-%m")
    cache_args = [schema, provider_type, provider_uuid, cache_arg_date]
    ocp_on_cloud_infra_map = {}

    if not synchronous:
        worker_cache = WorkerCache()
        timeout = settings.WORKER_CACHE_TIMEOUT
        rate_limited = False
        if is_customer_large(schema):
            rate_limited = rate_limit_tasks(task_name, schema)
            timeout = settings.WORKER_CACHE_LARGE_CUSTOMER_TIMEOUT

        if rate_limited or worker_cache.single_task_is_running(task_name, cache_args):
            msg = f"Task {task_name} already running for {cache_args}. Requeuing."
            if rate_limited:
                msg = f"Schema {schema} is currently rate limited. Requeuing."
            LOG.debug(log_json(tracing_id, msg=msg))
            update_summary_tables.s(
                schema,
                provider_type,
                provider_uuid,
                start_date,
                end_date=end_date,
                manifest_id=manifest_id,
                ingress_report_uuid=ingress_report_uuid,
                invoice_month=invoice_month,
                queue_name=queue_name,
                tracing_id=tracing_id,
                ocp_on_cloud=ocp_on_cloud,
            ).apply_async(queue=queue_name or UPDATE_SUMMARY_TABLES_QUEUE)
            return
        worker_cache.lock_single_task(task_name, cache_args, timeout=timeout)

    LOG.info(
        log_json(
            tracing_id,
            msg="starting summary table update",
            context=context,
            start_date=start_date,
            end_date=end_date,
            invoice_month=invoice_month,
        )
    )

    try:
        updater = ReportSummaryUpdater(schema, provider_uuid, manifest_id, tracing_id)
        start_date, end_date = updater.update_summary_tables(
            start_date, end_date, tracing_id, invoice_month=invoice_month
        )
        if ocp_on_cloud:
            ocp_on_cloud_infra_map = updater.get_openshift_on_cloud_infra_map(start_date, end_date, tracing_id)
    except ReportSummaryUpdaterCloudError as ex:
        LOG.info(log_json(tracing_id, msg=f"failed to correlate OpenShift metrics: error: {ex}", context=context))

    except ReportSummaryUpdaterProviderNotFoundError as pnf_ex:
        LOG.warning(
            log_json(
                tracing_id,
                msg=(
                    f"{pnf_ex} Possible source/provider delete during processing. "
                    + "Processing for this provier will halt."
                ),
            )
        )
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)
        return
    except Exception as ex:
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)
        raise ex

    if provider_type in (
        Provider.PROVIDER_AWS,
        Provider.PROVIDER_AWS_LOCAL,
        Provider.PROVIDER_AZURE,
        Provider.PROVIDER_AZURE_LOCAL,
    ):
        cost_model = None
        LOG.info(
            log_json(
                tracing_id,
                msg="markup calculated during summarization so not running update_cost_model_costs",
                context=context,
            )
        )
    else:
        with CostModelDBAccessor(schema, provider_uuid) as cost_model_accessor:
            cost_model = cost_model_accessor.cost_model

    # Create queued tasks for each OpenShift on Cloud cluster
    delete_signature_list = []
    if ocp_on_cloud_infra_map:
        trunc_delete_map = updater._ocp_cloud_updater.determine_truncates_and_deletes(start_date, end_date)
        for table_name, operation in trunc_delete_map.items():
            delete_signature_list.append(
                delete_openshift_on_cloud_data.si(
                    schema,
                    provider_uuid,
                    start_date,
                    end_date,
                    table_name,
                    operation,
                    manifest_id=manifest_id,
                    tracing_id=tracing_id,
                ).set(queue=queue_name or DELETE_TRUNCATE_QUEUE)
            )

    signature_list = []
    for openshift_provider_uuid, infrastructure_tuple in ocp_on_cloud_infra_map.items():
        infra_provider_uuid = infrastructure_tuple[0]
        infra_provider_type = infrastructure_tuple[1]
        signature_list.append(
            update_openshift_on_cloud.si(
                schema,
                openshift_provider_uuid,
                infra_provider_uuid,
                infra_provider_type,
                str(start_date),
                str(end_date),
                manifest_id=manifest_id,
                queue_name=queue_name,
                synchronous=synchronous,
                tracing_id=tracing_id,
            ).set(queue=queue_name or UPDATE_SUMMARY_TABLES_QUEUE)
        )

    # Apply OCP on Cloud tasks
    if signature_list:
        LOG.info(log_json(tracing_id, msg="chaining deletes and summaries", context=context))
        deletes = group(delete_signature_list)
        summaries = group(signature_list)
        c = chain(deletes, summaries)
        if synchronous:
            c.apply()
        else:
            c.apply_async()

    if not manifest_list and manifest_id:
        manifest_list = [manifest_id]

    if cost_model is not None:
        LOG.info(log_json(tracing_id, msg="updating cost model costs", context=context))
        linked_tasks = update_cost_model_costs.s(
            schema, provider_uuid, start_date, end_date, tracing_id=tracing_id
        ).set(queue=queue_name or UPDATE_COST_MODEL_COSTS_QUEUE) | mark_manifest_complete.si(
            schema, provider_type, provider_uuid=provider_uuid, manifest_list=manifest_list, tracing_id=tracing_id
        ).set(
            queue=queue_name or MARK_MANIFEST_COMPLETE_QUEUE
        )
    else:
        LOG.info(log_json(tracing_id, msg="skipping cost model updates", context=context))
        linked_tasks = mark_manifest_complete.s(
            schema,
            provider_type,
            provider_uuid=provider_uuid,
            manifest_list=manifest_list,
            ingress_report_uuid=ingress_report_uuid,
            tracing_id=tracing_id,
        ).set(queue=queue_name or MARK_MANIFEST_COMPLETE_QUEUE)

    chain(linked_tasks).apply_async()

    if not synchronous:
        worker_cache.release_single_task(task_name, cache_args)


@celery_app.task(name="masu.processor.tasks.delete_openshift_on_cloud_data", queue=DELETE_TRUNCATE_QUEUE)  # noqa: C901
def delete_openshift_on_cloud_data(
    schema_name,
    infrastructure_provider_uuid,
    start_date,
    end_date,
    table_name,
    operation,
    manifest_id=None,
    tracing_id=None,
):
    """Clear existing data from tables for date range."""
    updater = ReportSummaryUpdater(schema_name, infrastructure_provider_uuid, manifest_id, tracing_id)

    if operation == TRUNCATE_TABLE:
        updater._ocp_cloud_updater.truncate_summary_table_data(table_name)
    elif operation == DELETE_TABLE:
        updater._ocp_cloud_updater.delete_summary_table_data(start_date, end_date, table_name)


@celery_app.task(
    name="masu.processor.tasks.update_openshift_on_cloud",
    bind=True,
    autoretry_for=(ReportSummaryUpdaterCloudError,),
    max_retries=settings.MAX_UPDATE_RETRIES,
    queue=UPDATE_SUMMARY_TABLES_QUEUE,
)
def update_openshift_on_cloud(
    self,
    schema_name,
    openshift_provider_uuid,
    infrastructure_provider_uuid,
    infrastructure_provider_type,
    start_date,
    end_date,
    manifest_id=None,
    queue_name=None,
    synchronous=False,
    tracing_id=None,
):
    """Update OpenShift on Cloud for a specific OpenShift and cloud source."""
    task_name = "masu.processor.tasks.update_openshift_on_cloud"
    if is_ocp_on_cloud_summary_disabled(schema_name):
        msg = f"OCP on Cloud summary disabled for {schema_name}."
        LOG.info(msg)
        return
    if isinstance(start_date, str):
        cache_arg_date = start_date[:-3]  # Strip days from string
    else:
        cache_arg_date = start_date.strftime("%Y-%m")
    cache_args = [schema_name, infrastructure_provider_uuid, cache_arg_date]
    if not synchronous:
        worker_cache = WorkerCache()
        timeout = settings.WORKER_CACHE_TIMEOUT
        rate_limited = False
        if is_customer_large(schema_name):
            rate_limited = rate_limit_tasks(task_name, schema_name)
            timeout = settings.WORKER_CACHE_LARGE_CUSTOMER_TIMEOUT
        if rate_limited or worker_cache.single_task_is_running(task_name, cache_args):
            msg = f"Task {task_name} already running for {cache_args}. Requeuing."
            if rate_limited:
                msg = f"Schema {schema_name} is currently rate limited. Requeuing."
            LOG.debug(log_json(tracing_id, msg=msg))
            update_openshift_on_cloud.s(
                schema_name,
                openshift_provider_uuid,
                infrastructure_provider_uuid,
                infrastructure_provider_type,
                start_date,
                end_date,
                manifest_id=manifest_id,
                queue_name=queue_name,
                synchronous=synchronous,
                tracing_id=tracing_id,
            ).apply_async(queue=queue_name or UPDATE_SUMMARY_TABLES_QUEUE)
            return
        worker_cache.lock_single_task(task_name, cache_args, timeout=timeout)

    ctx = {
        "schema": schema_name,
        "ocp_provider_uuid": openshift_provider_uuid,
        "provider_type": infrastructure_provider_type,
        "provider_uuid": infrastructure_provider_uuid,
        "start_date": start_date,
        "end_date": end_date,
        "manifest_id": manifest_id,
        "queue_name": queue_name,
    }
    LOG.info(log_json(tracing_id, msg="updating ocp on cloud", context=ctx))

    try:
        updater = ReportSummaryUpdater(schema_name, infrastructure_provider_uuid, manifest_id, tracing_id)
        updater.update_openshift_on_cloud_summary_tables(
            start_date,
            end_date,
            openshift_provider_uuid,
            infrastructure_provider_uuid,
            infrastructure_provider_type,
            tracing_id,
        )
    except ReportSummaryUpdaterCloudError as ex:
        LOG.info(
            log_json(
                tracing_id,
                msg=f"updating ocp on cloud failed: retry {self.request.retries} of {settings.MAX_UPDATE_RETRIES}",
                context=ctx,
            ),
            exc_info=ex,
        )
        raise ReportSummaryUpdaterCloudError
    finally:
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)


@celery_app.task(name="masu.processor.tasks.update_all_summary_tables", queue=UPDATE_SUMMARY_TABLES_QUEUE)
def update_all_summary_tables(start_date, end_date=None):
    """Populate all the summary tables for reporting.

    Args:
        start_date  (str) The date to start populating the table.
        end_date    (str) The date to end on.

    Returns
        None

    """
    # Get all providers for all schemas
    all_accounts = []
    try:
        all_accounts = AccountsAccessor().get_accounts()
        for account in all_accounts:
            log_statement = (
                f"Gathering data for for\n"
                f' schema_name: {account.get("schema_name")}\n'
                f' provider: {account.get("provider_type")}\n'
                f' account (provider uuid): {account.get("provider_uuid")}'
            )
            LOG.info(log_statement)
            schema_name = account.get("schema_name")
            provider = account.get("provider_type")
            provider_uuid = account.get("provider_uuid")
            queue_name = OCP_QUEUE if provider and provider.lower() == "ocp" else None
            update_summary_tables.s(
                schema_name, provider, provider_uuid, str(start_date), end_date, queue_name=queue_name
            ).apply_async(queue=queue_name or UPDATE_SUMMARY_TABLES_QUEUE)
    except AccountsAccessorError as error:
        LOG.error("Unable to get accounts. Error: %s", str(error))


@celery_app.task(name="masu.processor.tasks.update_cost_model_costs", queue=UPDATE_COST_MODEL_COSTS_QUEUE)
def update_cost_model_costs(
    schema_name,
    provider_uuid,
    start_date=None,
    end_date=None,
    queue_name=None,
    synchronous=False,
    tracing_id=None,
):
    """Update usage charge information.

    Args:
        schema_name (str) The DB schema name.
        provider_uuid (str) The provider uuid.
        start_date (str, Optional) - Start date of range to update derived cost.
        end_date (str, Optional) - End date of range to update derived cost.

    Returns
        None

    """
    task_name = "masu.processor.tasks.update_cost_model_costs"
    cache_args = [schema_name, provider_uuid, start_date, end_date]
    if not synchronous:
        worker_cache = WorkerCache()
        if worker_cache.single_task_is_running(task_name, cache_args):
            msg = f"Task {task_name} already running for {cache_args}. Requeuing."
            LOG.debug(log_json(tracing_id, msg=msg))
            update_cost_model_costs.s(
                schema_name,
                provider_uuid,
                start_date=start_date,
                end_date=end_date,
                queue_name=queue_name,
                synchronous=synchronous,
                tracing_id=tracing_id,
            ).apply_async(queue=queue_name or UPDATE_COST_MODEL_COSTS_QUEUE)
            return
        worker_cache.lock_single_task(task_name, cache_args, timeout=settings.WORKER_CACHE_TIMEOUT)

    worker_stats.COST_MODEL_COST_UPDATE_ATTEMPTS_COUNTER.inc()

    context = {
        "schema": schema_name,
        "provider_uuid": provider_uuid,
        "start_date": start_date,
        "end_date": end_date,
    }
    LOG.info(log_json(tracing_id, msg="updating cost model costs", context=context))

    try:
        if updater := CostModelCostUpdater(schema_name, provider_uuid, tracing_id):
            updater.update_cost_model_costs(start_date, end_date)
        if provider_uuid:
            ProviderDBAccessor(provider_uuid).set_data_updated_timestamp()
    except Exception as ex:
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)
        raise ex

    if not synchronous:
        worker_cache.release_single_task(task_name, cache_args)


@celery_app.task(name="masu.processor.tasks.mark_manifest_complete", queue=MARK_MANIFEST_COMPLETE_QUEUE)
def mark_manifest_complete(  # noqa: C901
    schema,
    provider_type,
    provider_uuid="",
    ingress_report_uuid=None,
    tracing_id=None,
    manifest_list=None,
):
    """Mark a manifest and provider as complete"""
    context = {
        "schema": schema,
        "provider_type": provider_type,
        "provider_uuid": provider_uuid,
        "ingress_report_uuid": ingress_report_uuid,
        "manifest_list": manifest_list,
    }
    LOG.info(log_json(tracing_id, msg="marking manifest complete", context=context))
    if provider_uuid:
        ProviderDBAccessor(provider_uuid).set_data_updated_timestamp()
    with ReportManifestDBAccessor() as manifest_accessor:
        manifest_accessor.mark_manifests_as_completed(manifest_list)
    if ingress_report_uuid:
        LOG.info(log_json(tracing_id, msg="marking ingress report complete", context=context))
        with IngressReportDBAccessor(schema) as ingressreport_accessor:
            ingressreport_accessor.mark_ingress_report_as_completed(ingress_report_uuid)


@celery_app.task(name="masu.processor.tasks.vacuum_schema", queue=DEFAULT)
def vacuum_schema(schema_name):
    """Vacuum the reporting tables in the specified schema."""
    table_sql = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
            AND table_name like 'reporting_%%'
            AND table_type != 'VIEW'
    """

    with schema_context(schema_name):
        with connection.cursor() as cursor:
            cursor.execute(table_sql, [schema_name])
            tables = cursor.fetchall()
            tables = [table[0] for table in tables]
            for table in tables:
                sql = f"VACUUM ANALYZE {schema_name}.{table}"
                cursor.execute(sql)
                LOG.info(sql)
                LOG.info(cursor.statusmessage)


def normalize_table_options(table_options):
    """Normalize autovaccume_tune_schema table_options to dict type."""
    if not table_options:
        table_options = {}
    elif isinstance(table_options, str):
        table_options = json.loads(table_options)
    return table_options


# The autovacuum settings should be tuned over time to account for a table's records
# growing or shrinking. Based on the number of live tuples recorded from the latest
# statistics run, the autovacuum_vacuum_scale_factor will be adjusted up or down.
# More table rows will adjust the factor downward which should cause the autovacuum
# process to run more frequently on those tables. The effect should be that the
# process runs more frequently, but has less to do so it should overall be faster and
# more efficient.
# At this time, no table parameter will be lowered past the known production engine
# setting of 0.2 by default. However this function's settings can be overridden via the
# AUTOVACUUM_TUNING environment variable. See below.
@celery_app.task(name="masu.processor.tasks.autovacuum_tune_schema", queue_name=DEFAULT)  # noqa: C901
def autovacuum_tune_schema(schema_name):  # noqa: C901
    """Set the autovacuum table settings based on table size for the specified schema."""
    table_sql = """
SELECT s.relname as "table_name",
       s.n_live_tup,
       coalesce(table_options.options, '{}'::jsonb)::jsonb as "options"
  FROM pg_stat_user_tables s
  LEFT
  JOIN (
         select oid,
                jsonb_object_agg(split_part(option, '=', 1), split_part(option, '=', 2)) as options
           from (
                  select oid,
                         unnest(reloptions) as "option"
                    from pg_class
                   where reloptions is not null
                ) table_options_raw
          where option ~ '^autovacuum_vacuum_scale_factor'
          group
             by oid
       ) as table_options
    ON table_options.oid = s.relid
 WHERE s.schemaname = %s
 ORDER
    BY s.n_live_tup desc;
"""

    # initialize settings
    scale_table = [(10000000, Decimal("0.01")), (1000000, Decimal("0.02")), (100000, Decimal("0.05"))]
    alter_count = 0
    no_scale = Decimal("100")
    zero = Decimal("0")
    reset = Decimal("-1")
    scale_factor = zero

    # override with environment
    # This environment variable's data will be a JSON string in the form of:
    # [[threshold, scale], ...]
    # Where:
    #     threshold is a integer number representing the approximate number of rows (tuples)
    #     scale is the autovacuum_vacuum_scale_factor value (deimal number as string. ex "0.05")
    #     See: https://www.postgresql.org/docs/10/runtime-config-autovacuum.html
    #          https://www.2ndquadrant.com/en/blog/autovacuum-tuning-basics/
    autovacuum_settings = json.loads(os.environ.get("AUTOVACUUM_TUNING", "[]"))
    if autovacuum_settings:
        scale_table = [[int(e[0]), Decimal(str(e[1]))] for e in autovacuum_settings]

    scale_table.sort(key=lambda e: e[0], reverse=True)

    # Execute the scale based on table analyzsis
    with schema_context(schema_name):
        with connection.cursor() as cursor:
            cursor.execute(table_sql, [schema_name])
            tables = cursor.fetchall()

            for table in tables:
                scale_factor = zero
                table_name, n_live_tup, table_options = table
                table_options = normalize_table_options(table_options)
                try:
                    table_scale_option = Decimal(table_options.get("autovacuum_vacuum_scale_factor", no_scale))
                except InvalidOperation:
                    table_scale_option = no_scale

                for threshold, scale in scale_table:
                    if n_live_tup >= threshold:
                        scale_factor = scale
                        break

                # If current scale factor is the same as the table setting, then do nothing
                # Reset if table tuples have changed
                if scale_factor > zero and table_scale_option <= scale:
                    continue
                elif scale_factor == zero and "autovacuum_vacuum_scale_factor" in table_options:
                    scale_factor = reset

                # Determine if we adjust downward or upward due to the threshold found.
                if scale_factor > zero:
                    value = [scale_factor]
                    sql = f"""ALTER TABLE {schema_name}.{table_name} set (autovacuum_vacuum_scale_factor = %s);"""
                    sql_log = (sql % str(scale_factor)).replace("'", "")
                elif scale_factor < zero:
                    value = None
                    sql = f"""ALTER TABLE {schema_name}.{table_name} reset (autovacuum_vacuum_scale_factor);"""
                    sql_log = sql

                # Only execute the parameter change if there is something that needs to be changed
                if scale_factor != zero:
                    alter_count += 1
                    cursor.execute(sql, value)
                    LOG.info(sql_log)
                    LOG.info(cursor.statusmessage)

    LOG.info(f"Altered autovacuum_vacuum_scale_factor on {alter_count} tables")


@celery_app.task(name="masu.processor.tasks.remove_stale_tenants", queue=DEFAULT)
def remove_stale_tenants():
    """Remove stale tenants from the tenant api"""
    table_sql = """
        SELECT c.schema_name
        FROM api_customer c
        JOIN api_tenant t
            ON c.schema_name = t.schema_name
        LEFT JOIN api_sources s
            ON c.org_id = s.org_id
        WHERE s.source_id IS null
            AND c.date_updated < now() - INTERVAL '2 weeks'
        ;
    """
    with connection.cursor() as cursor:
        cursor.execute(table_sql)
        data = cursor.fetchall()
        Tenant.objects.filter(schema_name__in=[i[0] for i in data]).delete()
        if data:
            with KokuTenantMiddleware.tenant_lock:
                KokuTenantMiddleware.tenant_cache.clear()
        for name in data:
            LOG.info(f"Deleted tenant: {name}")


@celery_app.task(name="masu.processor.tasks.process_openshift_on_cloud", queue=GET_REPORT_FILES_QUEUE, bind=True)
def process_openshift_on_cloud(self, schema_name, provider_uuid, bill_date, tracing_id=None):
    """Process OpenShift on Cloud parquet files using Trino."""
    provider = Provider.objects.get(uuid=provider_uuid)
    provider_type = provider.type.replace("-local", "")

    table_info = {
        Provider.PROVIDER_AWS: {"table": "aws_line_items_daily", "date_columns": ["lineitem_usagestartdate"]},
        Provider.PROVIDER_AZURE: {"table": "azure_line_items", "date_columns": ["usagedatetime", "date"]},
        Provider.PROVIDER_GCP: {
            "table": "gcp_line_items_daily",
            "date_columns": ["usage_start_time", "usage_end_time"],
        },
    }
    table_name = table_info.get(provider_type).get("table")
    if isinstance(bill_date, str):
        bill_date = ciso8601.parse_datetime(bill_date)
    year = bill_date.strftime("%Y")
    month = bill_date.strftime("%m")
    invoice_month = bill_date.strftime("%Y%m")

    # We do not have fine grain control over specific days in a month for
    # OpenShift on Cloud parquet generation. This task will clear and reprocess
    # the entire billing month passed in as a parameter.
    where_clause = f"WHERE source='{provider_uuid}' AND year='{year}' AND month='{month}'"
    table_count_sql = f"SELECT count(*) FROM {table_name} {where_clause}"

    count, _ = execute_trino_query(schema_name, table_count_sql)
    count = count[0][0]

    processor = OCPCloudParquetReportProcessor(
        schema_name,
        "",
        provider_uuid,
        provider_type,
        0,
        context={"tracing_id": tracing_id, "start_date": bill_date, "invoice_month": invoice_month},
    )
    remove_files_not_in_set_from_s3_bucket(
        tracing_id, processor.parquet_ocp_on_cloud_path_s3, 0, processor.error_context
    )
    for i, offset in enumerate(range(0, count, settings.PARQUET_PROCESSING_BATCH_SIZE)):
        query_sql = (
            f"SELECT * FROM {table_name}"
            f" {where_clause} "
            f"OFFSET {offset} LIMIT {settings.PARQUET_PROCESSING_BATCH_SIZE}"
        )
        results, columns = execute_trino_query(schema_name, query_sql)
        data_frame = pd.DataFrame(data=results, columns=columns)
        data_frame = data_frame.drop(columns=[col for col in {"source", "year", "month"} if col in data_frame.columns])
        for column in table_info.get(provider_type).get("date_columns"):
            if column in data_frame.columns:
                data_frame[column] = pd.to_datetime(data_frame[column])

        file_name = f"ocp_on_{provider_type}_{i}"
        processor.process(file_name, [data_frame])


@celery_app.task(name="masu.processor.tasks.process_openshift_on_cloud_daily", queue=GET_REPORT_FILES_QUEUE, bind=True)
def process_daily_openshift_on_cloud(
    self, schema_name, provider_uuid, bill_date, start_date, end_date, tracing_id=None
):
    """Process daily partitioned OpenShift on Cloud parquet files using Trino."""
    provider = Provider.objects.get(uuid=provider_uuid)
    provider_type = provider.type.replace("-local", "")

    table_info = {
        Provider.PROVIDER_GCP: {
            "table": "gcp_line_items_daily",
            "date_columns": ["usage_start_time", "usage_end_time"],
            "date_where_clause": "usage_start_time >= TIMESTAMP '{0}' AND usage_start_time < date_add('day', 1, TIMESTAMP '{0}')",  # noqa: E501
        },
    }
    table_name = table_info.get(provider_type).get("table")
    provider_where_clause = table_info.get(provider_type).get("date_where_clause")
    if isinstance(bill_date, str):
        bill_date = ciso8601.parse_datetime(bill_date)
    year = bill_date.strftime("%Y")
    month = bill_date.strftime("%m")
    invoice_month = bill_date.strftime("%Y%m")

    base_where_clause = f"WHERE source='{provider_uuid}' AND year='{year}' AND month='{month}'"

    days = DateHelper().list_days(start_date, end_date)
    for day in days:
        today_where_clause = f"{base_where_clause} AND {provider_where_clause.format(day)}"
        table_count_sql = f"SELECT count(*) FROM {table_name} {today_where_clause}"
        count, _ = execute_trino_query(schema_name, table_count_sql)
        count = count[0][0]

        processor = OCPCloudParquetReportProcessor(
            schema_name,
            "",
            provider_uuid,
            provider_type,
            0,
            context={"tracing_id": tracing_id, "start_date": day.date(), "invoice_month": invoice_month},
        )
        daily_s3_path = get_path_prefix(
            processor.account,
            processor.provider_type,
            processor.provider_uuid,
            day,
            Config.PARQUET_DATA_TYPE,
            report_type=processor.report_type,
            daily=True,
            partition_daily=True,
        )
        remove_files_not_in_set_from_s3_bucket(tracing_id, daily_s3_path, 0, processor.error_context)
        for i, offset in enumerate(range(0, count, settings.PARQUET_PROCESSING_BATCH_SIZE)):
            query_sql = (
                f"SELECT * FROM {table_name}"
                f" {today_where_clause} "
                f"OFFSET {offset} LIMIT {settings.PARQUET_PROCESSING_BATCH_SIZE}"
            )
            results, columns = execute_trino_query(schema_name, query_sql)
            data_frame = pd.DataFrame(data=results, columns=columns)
            data_frame = data_frame.drop(
                columns=[col for col in {"source", "year", "month", "day"} if col in data_frame.columns]
            )
            for column in table_info.get(provider_type).get("date_columns"):
                if column in data_frame.columns:
                    data_frame[column] = pd.to_datetime(data_frame[column])

            file_name = f"ocp_on_{provider_type}_{i}"
            processor.process(file_name, [data_frame])
