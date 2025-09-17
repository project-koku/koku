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
from common.queues import CostModelQueue
from common.queues import DEFAULT
from common.queues import DownloadQueue
from common.queues import get_customer_queue
from common.queues import OCPQueue
from common.queues import PriorityQueue
from common.queues import RefreshQueue
from common.queues import SummaryQueue
from koku import celery_app
from koku.middleware import KokuTenantMiddleware
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.exceptions import MasuProcessingError
from masu.exceptions import MasuProviderError
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
from masu.external.report_downloader import ReportDownloaderError
from masu.processor import is_ocp_on_cloud_summary_disabled
from masu.processor import is_rate_limit_customer_large
from masu.processor import is_source_disabled
from masu.processor import is_summary_processing_disabled
from masu.processor import is_validation_enabled
from masu.processor._tasks.data_validation import DataValidator
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor._tasks.remove_expired import _remove_expired_data
from masu.processor._tasks.remove_expired import _remove_expired_trino_partitions
from masu.processor.cost_model_cost_updater import CostModelCostUpdater
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import DELETE_TABLE
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import TRUNCATE_TABLE
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError
from masu.processor.report_summary_updater import ReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdaterCloudError
from masu.processor.report_summary_updater import ReportSummaryUpdaterProviderNotFoundError
from masu.processor.worker_cache import rate_limit_tasks
from masu.processor.worker_cache import WorkerCache
from masu.util.common import get_latest_openshift_on_cloud_manifest
from masu.util.common import set_summary_timestamp
from reporting.ingress.models import IngressReports
from reporting_common.models import CostUsageReportStatus
from reporting_common.models import DelayedCeleryTasks
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep

LOG = logging.getLogger(__name__)

UPDATE_SUMMARY_TABLES_TASK = "masu.processor.tasks.update_summary_tables"


def deduplicate_summary_reports(reports_to_summarize, manifest_list):
    """Take a list of reports to summarize and deduplicate them."""
    reports_by_source = defaultdict(list)
    schema_name = None
    for report in reports_to_summarize:
        if report:
            reports_by_source[report.get("provider_uuid")].append(report)

            if schema_name is None:
                # Only set the schema name once
                schema_name = report.get("schema_name")

    reports_deduplicated = []

    kwargs = {}
    if schema_name:
        kwargs["schema_name"] = schema_name

    LOG.info(log_json("summarize_reports", msg="deduplicating reports", **kwargs))
    for report_list in reports_by_source.values():
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

    LOG.info(
        log_json(
            "summarize_reports",
            msg=f"deduplicated reports, num report: {len(reports_deduplicated)}",
            **kwargs,
        )
    )
    return reports_deduplicated


def trigger_ocp_on_cloud_summary(
    context, schema, provider_uuid, manifest_id, tracing_id, start_date, end_date, queue_name=None, synchronous=False
):
    """Queue up the ocp on cloud delete and summary tasks for a provider."""
    if is_ocp_on_cloud_summary_disabled(schema):
        LOG.info(
            log_json(
                tracing_id, msg="ocp on cloud summary disabled for schema, skipping ocp cloud summary", context=context
            )
        )
        return
    updater = ReportSummaryUpdater(schema, provider_uuid, manifest_id, tracing_id)
    ocp_on_cloud_infra_map = None
    try:
        ocp_on_cloud_infra_map = updater.get_openshift_on_cloud_infra_map(start_date, end_date, tracing_id)
    except ReportSummaryUpdaterCloudError as ex:
        LOG.info(log_json(tracing_id, msg=f"failed to correlate OpenShift metrics: error: {ex}", context=context))
    if not ocp_on_cloud_infra_map:
        LOG.info(log_json(tracing_id, msg="ocp on cloud infra map empty, skipping ocp cloud summary", context=context))
        return
    fallback_update_summary_tables_queue = get_customer_queue(schema, SummaryQueue)
    delete_truncate_queue = get_customer_queue(schema, RefreshQueue)
    delete_signature_list = []
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
            ).set(queue=delete_truncate_queue)
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
            ).set(queue=fallback_update_summary_tables_queue)
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


def delayed_summarize_current_month(schema_name: str, provider_uuids: list, provider_type: str):
    """Delay Resummarize provider data for the current month."""
    queue = get_customer_queue(schema_name, SummaryQueue)

    for provider_uuid in provider_uuids:
        id = DelayedCeleryTasks.create_or_reset_timeout(
            task_name=UPDATE_SUMMARY_TABLES_TASK,
            task_args=[schema_name],
            task_kwargs={
                "provider_type": provider_type,
                "provider_uuid": str(provider_uuid),
                "start_date": str(DateHelper().this_month_start),
            },
            provider_uuid=provider_uuid,
            queue_name=queue,
        )
        if schema_name == settings.QE_SCHEMA:
            # bypass the wait for QE
            id.delete()


def record_all_manifest_files(manifest_id, report_files, tracing_id):
    """Store all report file names for manifest ID."""
    for report in report_files:
        try:
            _, created = CostUsageReportStatus.objects.get_or_create(report_name=report, manifest_id=manifest_id)
            LOG.debug(log_json(tracing_id, msg=f"Logging {report} for manifest ID: {manifest_id}, created: {created}"))
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
    if stats := CostUsageReportStatus.objects.filter(report_name=file_name, manifest_id=manifest_id).first():
        already_processed = stats.completed_datetime
        if already_processed:
            msg = f"Report {file_name} has already been processed."
        else:
            msg = f"Recording stats entry for {file_name}"
        LOG.info(log_json(tracing_id, msg=msg, context=context))
    return already_processed


@celery_app.task(name="masu.processor.tasks.get_report_files", queue=DownloadQueue.DEFAULT, bind=True)  # noqa: C901
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
    if is_source_disabled(provider_uuid):
        return
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
        # Get the task ID and add it to the report_context for tracking
        report_context["task_id"] = get_report_files.request.id
        try:
            # The real download task happens in _get_report_files
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
            ReportManifestDBAccessor().update_manifest_state(
                ManifestStep.DOWNLOAD, ManifestState.FAILED, report_context["manifest_id"]
            )
            return

        if report_dict:
            context["file"] = report_dict["file"]
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
            "metadata_start_date": report_dict.get("metadata_start_date"),
            "metadata_end_date": report_dict.get("metadata_end_date"),
        }

        try:
            LOG.info(log_json(tracing_id, msg="processing starting", context=context))
            worker_stats.PROCESS_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()

            report_dict["tracing_id"] = tracing_id
            report_dict["provider_type"] = provider_type

            # The real processing (convert to parquet and push to S3) happens in _process_report_file
            result = _process_report_file(
                schema_name, provider_type, report_dict, ingress_reports, ingress_reports_uuid
            )

        except (ReportProcessorError, ReportProcessorDBError) as processing_error:
            worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
            LOG.error(log_json(tracing_id, msg=f"Report processing error: {processing_error}", context=context))
            ReportManifestDBAccessor().update_manifest_state(
                ManifestStep.PROCESSING, ManifestState.FAILED, report_context["manifest_id"]
            )
            WorkerCache().remove_task_from_cache(cache_key)
            raise processing_error
        except NotImplementedError as err:
            LOG.info(log_json(tracing_id, msg=f"Not implemented error: {err}", context=context))
            ReportManifestDBAccessor().update_manifest_state(
                ManifestStep.PROCESSING, ManifestState.FAILED, report_context["manifest_id"]
            )
            WorkerCache().remove_task_from_cache(cache_key)

        WorkerCache().remove_task_from_cache(cache_key)
        if not result:
            LOG.info(log_json(tracing_id, msg="no report files processed, skipping summary", context=context))
            # update provider even when there are no new reports so we continue polling
            if provider := Provider.objects.filter(uuid=provider_uuid).first():
                provider.set_data_updated_timestamp()
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


@celery_app.task(name="masu.processor.tasks.remove_expired_trino_partitions", queue=DEFAULT)
def remove_expired_trino_partitions(schema_name, provider_type, simulate):
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
        "provider_type": provider_type,
    }
    LOG.info(log_json("remove_expired_data", msg="removing expired partitions", context=context))
    _remove_expired_trino_partitions(schema_name, provider_type, simulate)


@celery_app.task(name="masu.processor.tasks.summarize_reports", queue=SummaryQueue.DEFAULT)  # noqa: C901
def summarize_reports(  # noqa: C901
    reports_to_summarize, queue_name=None, manifest_list=None, ingress_report_uuid=None
):
    """
    Summarize reports returned from line summary task.

    Args:
        reports_to_summarize (list) list of reports to process

    Returns:
        None

    """
    reports_deduplicated = deduplicate_summary_reports(reports_to_summarize, manifest_list)
    for report in reports_deduplicated:
        schema_name = report.get("schema_name")
        # For day-to-day summarization we choose a small window to
        # cover new data from a window of days.
        # This saves us from re-summarizing unchanged data and cuts down
        # on processing time. There are override mechanisms in the
        # Updater classes for when full-month summarization is
        # required.
        with ReportManifestDBAccessor() as manifest_accesor:
            fallback_queue = get_customer_queue(schema_name, SummaryQueue)
            tracing_id = report.get("tracing_id", report.get("manifest_uuid", "no-tracing-id"))

            if not manifest_accesor.manifest_ready_for_summary(report.get("manifest_id")):
                LOG.info(log_json(tracing_id, msg="manifest not ready for summary", context=report))
                continue

            LOG.info(log_json(tracing_id, msg="report to summarize", context=report))

            months = get_months_in_date_range(
                start=report.get("start"),
                end=report.get("end"),
                report=True,
            )
            for month in months:
                update_summary_tables.s(
                    schema_name,
                    report.get("provider_type"),
                    report.get("provider_uuid"),
                    start_date=month[0],
                    end_date=month[1],
                    ingress_report_uuid=ingress_report_uuid,
                    manifest_id=report.get("manifest_id"),
                    queue_name=queue_name,
                    tracing_id=tracing_id,
                    manifest_list=manifest_list,
                ).apply_async(queue=queue_name or fallback_queue)


@celery_app.task(name=UPDATE_SUMMARY_TABLES_TASK, queue=SummaryQueue.DEFAULT)  # noqa: C901
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
    if is_summary_processing_disabled(schema) or is_source_disabled(provider_uuid):
        return
    if is_ocp_on_cloud_summary_disabled(schema):
        ocp_on_cloud = False

    worker_stats.REPORT_SUMMARY_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()
    task_name = "masu.processor.tasks.update_summary_tables"
    if isinstance(start_date, str):
        cache_arg_date = start_date[:-3]  # Strip days from string
    else:
        cache_arg_date = start_date.strftime("%Y-%m")
    cache_args = [schema, provider_type, provider_uuid, cache_arg_date]
    is_large_customer_rate_limited = is_rate_limit_customer_large(schema)
    # Fallback should only be used for non-ocp processing
    fallback_update_summary_tables_queue = get_customer_queue(schema, SummaryQueue)
    update_cost_model_queue = get_customer_queue(schema, CostModelQueue)
    priority_queue = get_customer_queue(schema, PriorityQueue)
    timeout = settings.WORKER_CACHE_TIMEOUT
    if fallback_update_summary_tables_queue != SummaryQueue.DEFAULT:
        timeout = settings.WORKER_CACHE_LARGE_CUSTOMER_TIMEOUT

    if not synchronous:
        worker_cache = WorkerCache()
        rate_limited = False
        if is_large_customer_rate_limited:
            rate_limited = rate_limit_tasks(task_name, schema)

        if rate_limited or worker_cache.single_task_is_running(task_name, cache_args):
            msg = f"Task {task_name} already running for {cache_args}. Requeuing."
            if rate_limited:
                msg = f"Schema {schema} is currently rate limited. Requeuing."
            LOG.info(log_json(tracing_id, msg=msg))
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
            ).apply_async(queue=queue_name or fallback_update_summary_tables_queue)
            return
        worker_cache.lock_single_task(task_name, cache_args, timeout=timeout)

    # Mark summary start time
    set_summary_timestamp(ManifestState.START, manifest_id)
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

    except ReportSummaryUpdaterProviderNotFoundError as ex:
        LOG.warning(
            log_json(
                tracing_id,
                msg="possible source/provider delete during processing - halting processing",
                context=context,
            ),
            exc_info=ex,
        )
        # Mark summary failed time
        set_summary_timestamp(ManifestState.FAILED, manifest_id)
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)
        return
    except Exception as ex:
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)
        # Mark summary failed time
        set_summary_timestamp(ManifestState.FAILED, manifest_id)
        raise ex

    # Mark summary complete time
    set_summary_timestamp(ManifestState.END, manifest_id)

    LOG.info(log_json(tracing_id, msg="triggering ocp on cloud summary", context=context))
    trigger_ocp_on_cloud_summary(
        context, schema, provider_uuid, manifest_id, tracing_id, start_date, end_date, queue_name, synchronous
    )

    if not manifest_list and manifest_id:
        manifest_list = [manifest_id]

    # OCP cost distribution of unattributed costs occurs within the `update_cost_model_costs` method.
    # This method should always be called for OCP providers even when it does not have a cost model
    if provider_type == Provider.PROVIDER_OCP:
        LOG.info(log_json(tracing_id, msg="Queue OCP cost model/manifest complete tasks", context=context))
        linked_tasks = (
            update_cost_model_costs.s(schema, provider_uuid, start_date, end_date, tracing_id=tracing_id).set(
                queue=update_cost_model_queue
            )
            | mark_manifest_complete.si(
                schema, provider_type, provider_uuid, manifest_list=manifest_list, tracing_id=tracing_id
            ).set(queue=priority_queue)
            | validate_daily_data.si(schema, start_date, end_date, provider_uuid, context=context).set(
                queue=priority_queue
            )
        )

    else:
        LOG.info(log_json(tracing_id, msg="Queue Cloud manifest complete tasks", context=context))
        linked_tasks = mark_manifest_complete.s(
            schema,
            provider_type,
            provider_uuid,
            manifest_list=manifest_list,
            ingress_report_uuid=ingress_report_uuid,
            tracing_id=tracing_id,
        ).set(queue=priority_queue) | validate_daily_data.si(
            schema, start_date, end_date, provider_uuid, context=context
        ).set(
            queue=priority_queue
        )

    chain(linked_tasks).apply_async()

    if not synchronous:
        worker_cache.release_single_task(task_name, cache_args)


@celery_app.task(name="masu.processor.tasks.delete_openshift_on_cloud_data", queue=RefreshQueue.DEFAULT)  # noqa: C901
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
    queue=SummaryQueue.DEFAULT,
)
def update_openshift_on_cloud(  # noqa: C901
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
    # Get latest manifest id for running OCP provider
    context = {
        "ocp": openshift_provider_uuid,
        "schema": schema_name,
        "infra_uuid": infrastructure_provider_uuid,
        "start": start_date,
        "end": end_date,
    }
    LOG.info(log_json(tracing_id, msg="update openshift on cloud processing started", context=context))
    ocp_manifest_id = get_latest_openshift_on_cloud_manifest(start_date, openshift_provider_uuid)
    task_name = "masu.processor.tasks.update_openshift_on_cloud"
    if is_ocp_on_cloud_summary_disabled(schema_name):
        msg = f"OCP on Cloud summary disabled for {schema_name}."
        LOG.info(msg)
        return
    if isinstance(start_date, str):
        cache_arg_date = start_date[:-3]  # Strip days from string
    else:
        cache_arg_date = start_date.strftime("%Y-%m")
    cache_args = [schema_name, infrastructure_provider_uuid, openshift_provider_uuid, cache_arg_date]
    if not synchronous:
        worker_cache = WorkerCache()
        timeout = settings.WORKER_CACHE_TIMEOUT
        rate_limited = False
        fallback_queue = get_customer_queue(schema_name, SummaryQueue)
        if is_rate_limit_customer_large(schema_name):
            rate_limited = rate_limit_tasks(task_name, schema_name)
        if fallback_queue != SummaryQueue.DEFAULT:
            timeout = settings.WORKER_CACHE_LARGE_CUSTOMER_TIMEOUT
        if rate_limited or worker_cache.single_task_is_running(task_name, cache_args):
            msg = f"Task {task_name} already running for {cache_args}. Requeuing."
            if rate_limited:
                msg = f"Schema {schema_name} is currently rate limited. Requeuing."
            LOG.info(log_json(tracing_id, msg=msg))
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
            ).apply_async(queue=queue_name or fallback_queue)
            return
        worker_cache.lock_single_task(task_name, cache_args, timeout=timeout)

    # Set OpenShift summary started time
    set_summary_timestamp(ManifestState.START, ocp_manifest_id)
    ctx = {
        "schema": schema_name,
        "ocp_provider_uuid": openshift_provider_uuid,
        "provider_type": infrastructure_provider_type,
        "provider_uuid": infrastructure_provider_uuid,
        "start_date": start_date,
        "end_date": end_date,
        "cloud_manifest_id": manifest_id,
        "ocp_manifest_id": ocp_manifest_id,
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
        # Regardless of an attached cost model we must run an update for default distribution costs
        LOG.info(log_json(tracing_id, msg="updating cost model costs", context=ctx))
        cost_model_fallback_queue = get_customer_queue(schema_name, CostModelQueue)
        priority_queue = get_customer_queue(schema_name, PriorityQueue)
        update_cost_model_costs.s(
            schema_name, openshift_provider_uuid, start_date, end_date, tracing_id=tracing_id
        ).apply_async(queue=queue_name or cost_model_fallback_queue)
        # Set OpenShift manifest summary end time
        set_summary_timestamp(ManifestState.END, ocp_manifest_id)
        validate_daily_data.s(
            schema_name,
            start_date,
            end_date,
            openshift_provider_uuid,
            ocp_on_cloud_type=infrastructure_provider_type,
            context=ctx,
        ).apply_async(queue=priority_queue)
    except ReportSummaryUpdaterCloudError as ex:
        LOG.info(
            log_json(
                tracing_id,
                msg=f"updating ocp on cloud failed: retry {self.request.retries} of {settings.MAX_UPDATE_RETRIES}",
                context=ctx,
            ),
            exc_info=ex,
        )
        # Set OpenShift manifest summary failed time
        set_summary_timestamp(ManifestState.FAILED, ocp_manifest_id)
        raise ReportSummaryUpdaterCloudError from ex
    except ReportSummaryUpdaterProviderNotFoundError as ex:
        LOG.warning(
            log_json(
                tracing_id, msg="possible source/provider delete during processing - halting processing", context=ctx
            ),
            exc_info=ex,
        )
        # Set OpenShift manifest summary failed time
        set_summary_timestamp(ManifestState.FAILED, ocp_manifest_id)
    finally:
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)


@celery_app.task(name="masu.processor.tasks.update_all_summary_tables", queue=SummaryQueue.DEFAULT)
def update_all_summary_tables(start_date, end_date=None):
    """Populate all the summary tables for reporting.

    Args:
        start_date  (str) The date to start populating the table.
        end_date    (str) The date to end on.

    Returns
        None

    """
    # Get all providers for all schemas
    all_accounts = Provider.objects.get_accounts()
    for account in all_accounts:
        log_statement = (
            f"Gathering data for for\n"
            f" schema_name: {account.get('schema_name')}\n"
            f" provider: {account.get('provider_type')}\n"
            f" account (provider uuid): {account.get('provider_uuid')}"
        )
        LOG.info(log_statement)
        schema_name = account.get("schema_name")
        provider_type = account.get("provider_type")
        provider_uuid = account.get("provider_uuid")
        fallback_queue = get_customer_queue(schema_name, SummaryQueue)
        ocp_process_queue = get_customer_queue(schema_name, OCPQueue)
        queue_name = ocp_process_queue if provider_type and provider_type.lower() == "ocp" else None
        update_summary_tables.s(
            schema_name, provider_type, provider_uuid, str(start_date), end_date, queue_name=queue_name
        ).apply_async(queue=queue_name or fallback_queue)


@celery_app.task(name="masu.processor.tasks.update_cost_model_costs", queue=CostModelQueue.DEFAULT)
def update_cost_model_costs(  # noqa: C901
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
    # Check if provider exists and has processed data before attempting to lock the task
    provider = Provider.objects.filter(uuid=provider_uuid).first()
    if provider and not provider.data_updated_timestamp:
        LOG.info(
            log_json(
                tracing_id,
                msg=f"Skipping cost model update for source {provider_uuid}. No data has been processed yet.",
                context={"schema": schema_name},
            )
        )
        return

    task_name = "masu.processor.tasks.update_cost_model_costs"
    cache_args = [schema_name, provider_uuid, start_date, end_date]
    if not synchronous:
        worker_cache = WorkerCache()
        timeout = settings.WORKER_CACHE_TIMEOUT
        fallback_queue = get_customer_queue(schema_name, CostModelQueue)
        rate_limited = False
        if is_rate_limit_customer_large(schema_name):
            rate_limited = rate_limit_tasks(task_name, schema_name)
            timeout = settings.WORKER_CACHE_LARGE_CUSTOMER_TIMEOUT
        if rate_limited or worker_cache.single_task_is_running(task_name, cache_args):
            msg = f"Task {task_name} already running for {cache_args}. Requeuing."
            if rate_limited:
                msg = f"Schema {schema_name} is currently rate limited. Requeuing."
            LOG.debug(log_json(tracing_id, msg=msg))
            update_cost_model_costs.s(
                schema_name,
                provider_uuid,
                start_date=start_date,
                end_date=end_date,
                queue_name=queue_name,
                synchronous=synchronous,
                tracing_id=tracing_id,
            ).apply_async(queue=queue_name or fallback_queue)
            return
        worker_cache.lock_single_task(task_name, cache_args, timeout=timeout)

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
        if provider := Provider.objects.filter(uuid=provider_uuid).first():
            provider.set_data_updated_timestamp()
    except Exception as ex:
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)
        raise ex

    if not synchronous:
        worker_cache.release_single_task(task_name, cache_args)


@celery_app.task(name="masu.processor.tasks.mark_manifest_complete", queue=PriorityQueue.DEFAULT)
def mark_manifest_complete(
    schema,
    provider_type,
    provider_uuid,
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
    if provider := Provider.objects.filter(uuid=provider_uuid).first():
        provider.set_data_updated_timestamp()
    if manifest_list:
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest_accessor.mark_manifests_as_completed(manifest_list)
    else:
        LOG.info(log_json(tracing_id, msg="no manifest to mark complete, likely masu resummary task", context=context))
    if ingress_report_uuid:
        with schema_context(schema):
            report = IngressReports.objects.get(uuid=ingress_report_uuid)
            report.mark_completed()


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


@celery_app.task(name="masu.processor.tasks.validate_daily_data", queue=PriorityQueue.DEFAULT)
def validate_daily_data(schema, start_date, end_date, provider_uuid, ocp_on_cloud_type=None, context=None):
    # collect and validate cost metrics between postgres and trino tables.
    if is_validation_enabled(schema):
        data_validator = DataValidator(schema, start_date, end_date, provider_uuid, ocp_on_cloud_type, context)
        data_validator.check_data_integrity()
    else:
        LOG.info(log_json(msg="skipping validation, disabled for schema", context=context))
