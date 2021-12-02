#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Asynchronous tasks."""
import datetime
import json
import logging
import os
from decimal import Decimal
from decimal import InvalidOperation

from celery import chain
from dateutil import parser
from django.db import connection
from django.db.utils import IntegrityError
from tenant_schemas.utils import schema_context

import masu.prometheus_stats as worker_stats
from api.common import log_json
from api.iam.models import Tenant
from api.provider.models import Provider
from koku import celery_app
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from koku.middleware import KokuTenantMiddleware
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.exceptions import MasuProcessingError
from masu.exceptions import MasuProviderError
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
from masu.external.report_downloader import ReportDownloaderError
from masu.processor import enable_trino_processing
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor._tasks.remove_expired import _remove_expired_data
from masu.processor.cost_model_cost_updater import CostModelCostUpdater
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError
from masu.processor.report_summary_updater import ReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdaterCloudError
from masu.processor.report_summary_updater import ReportSummaryUpdaterProviderNotFoundError
from masu.processor.worker_cache import WorkerCache


LOG = logging.getLogger(__name__)

DEFAULT = "celery"
GET_REPORT_FILES_QUEUE = "download"
OCP_QUEUE = "ocp"
PRIORITY_QUEUE = "priority"
REFRESH_MATERIALIZED_VIEWS_QUEUE = "refresh"
REMOVE_EXPIRED_DATA_QUEUE = "summary"
SUMMARIZE_REPORTS_QUEUE = "summary"
UPDATE_COST_MODEL_COSTS_QUEUE = "cost_model"
UPDATE_SUMMARY_TABLES_QUEUE = "summary"
VACUUM_SCHEMA_QUEUE = "summary"

# any additional queues should be added to this list
QUEUE_LIST = [
    DEFAULT,
    GET_REPORT_FILES_QUEUE,
    OCP_QUEUE,
    PRIORITY_QUEUE,
    REFRESH_MATERIALIZED_VIEWS_QUEUE,
    REMOVE_EXPIRED_DATA_QUEUE,
    SUMMARIZE_REPORTS_QUEUE,
    UPDATE_COST_MODEL_COSTS_QUEUE,
    UPDATE_SUMMARY_TABLES_QUEUE,
    VACUUM_SCHEMA_QUEUE,
]


def record_all_manifest_files(manifest_id, report_files, tracing_id):
    """Store all report file names for manifest ID."""
    for report in report_files:
        try:
            with ReportStatsDBAccessor(report, manifest_id):
                LOG.debug(log_json(tracing_id, f"Logging {report} for manifest ID: {manifest_id}"))
        except IntegrityError:
            # OCP records the entire file list for a new manifest when the listener
            # recieves a payload.  With multiple listeners it is possilbe for
            # two listeners to recieve a report file for the same manifest at
            # roughly the same time.  In that case the report file may already
            # exist and an IntegrityError would be thrown.
            LOG.debug(log_json(tracing_id, f"Report {report} has already been recorded."))


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
        LOG.info(log_json(tracing_id, msg, context))
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
    tracing_id=None,
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
    try:
        worker_stats.GET_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()
        month = report_month
        if isinstance(report_month, str):
            month = parser.parse(report_month)
        report_file = report_context.get("key")
        cache_key = f"{provider_uuid}:{report_file}"
        tracing_id = report_context.get("assembly_id", "no-tracing-id")
        WorkerCache().add_task_to_cache(cache_key)

        context = {"account": customer_name[4:], "provider_uuid": provider_uuid}

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
            )
        except (MasuProcessingError, MasuProviderError, ReportDownloaderError) as err:
            worker_stats.REPORT_FILE_DOWNLOAD_ERROR_COUNTER.labels(provider_type=provider_type).inc()
            WorkerCache().remove_task_from_cache(cache_key)
            LOG.warning(log_json(tracing_id, str(err), context))
            return

        stmt = (
            f"Reports to be processed: "
            f" schema_name: {customer_name} "
            f" provider: {provider_type} "
            f" provider_uuid: {provider_uuid}"
        )
        if report_dict:
            stmt += f" file: {report_dict['file']}"
            LOG.info(log_json(tracing_id, stmt, context))
        else:
            WorkerCache().remove_task_from_cache(cache_key)
            return None

        report_meta = {
            "schema_name": schema_name,
            "provider_type": provider_type,
            "provider_uuid": provider_uuid,
            "manifest_id": report_dict.get("manifest_id"),
            "tracing_id": tracing_id,
        }

        try:
            stmt = (
                f"Processing starting: "
                f" schema_name: {customer_name} "
                f" provider: {provider_type} "
                f" provider_uuid: {provider_uuid} "
                f' file: {report_dict.get("file")}'
            )
            LOG.info(log_json(tracing_id, stmt))
            worker_stats.PROCESS_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()

            report_dict["tracing_id"] = tracing_id
            report_dict["provider_type"] = provider_type

            _process_report_file(schema_name, provider_type, report_dict)

        except (ReportProcessorError, ReportProcessorDBError) as processing_error:
            worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
            LOG.error(log_json(tracing_id, str(processing_error), context))
            WorkerCache().remove_task_from_cache(cache_key)
            raise processing_error
        except NotImplementedError as err:
            LOG.info(log_json(tracing_id, str(err), context))
            WorkerCache().remove_task_from_cache(cache_key)

        WorkerCache().remove_task_from_cache(cache_key)

        return report_meta
    except ReportDownloaderWarning as err:
        LOG.warning(log_json(tracing_id, str(err), context))
        WorkerCache().remove_task_from_cache(cache_key)
    except Exception as err:
        worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
        LOG.error(log_json(tracing_id, str(err), context))
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
    stmt = (
        f"remove_expired_data called with args:\n"
        f" schema_name: {schema_name},\n"
        f" provider: {provider},\n"
        f" simulate: {simulate},\n"
        f" provider_uuid: {provider_uuid},\n",
    )
    LOG.info(stmt)
    _remove_expired_data(schema_name, provider, simulate, provider_uuid)
    refresh_materialized_views.s(schema_name, provider, provider_uuid=provider_uuid).apply_async(
        queue=queue_name or REFRESH_MATERIALIZED_VIEWS_QUEUE
    )


@celery_app.task(name="masu.processor.tasks.summarize_reports", queue=SUMMARIZE_REPORTS_QUEUE)
def summarize_reports(reports_to_summarize, queue_name=None):
    """
    Summarize reports returned from line summary task.

    Args:
        reports_to_summarize (list) list of reports to process

    Returns:
        None

    """
    reports_to_summarize = [report for report in reports_to_summarize if report]
    reports_deduplicated = [dict(t) for t in {tuple(d.items()) for d in reports_to_summarize}]

    for report in reports_deduplicated:
        # For day-to-day summarization we choose a small window to
        # cover new data from a window of days.
        # This saves us from re-summarizing unchanged data and cuts down
        # on processing time. There are override mechanisms in the
        # Updater classes for when full-month summarization is
        # required.
        with ReportManifestDBAccessor() as manifest_accesor:
            if manifest_accesor.manifest_ready_for_summary(report.get("manifest_id")):
                if report.get("start") and report.get("end"):
                    LOG.info("using start and end dates from the manifest")
                    start_date = parser.parse(report.get("start")).strftime("%Y-%m-%d")
                    end_date = parser.parse(report.get("end")).strftime("%Y-%m-%d")
                else:
                    LOG.info("generating start and end dates for manifest")
                    start_date = DateAccessor().today() - datetime.timedelta(days=2)
                    start_date = start_date.strftime("%Y-%m-%d")
                    end_date = DateAccessor().today().strftime("%Y-%m-%d")
                msg = f"report to summarize: {str(report)}"
                tracing_id = report.get("tracing_id", report.get("manifest_uuid", "no-tracing-id"))
                LOG.info(log_json(tracing_id, msg))
                update_summary_tables.s(
                    report.get("schema_name"),
                    report.get("provider_type"),
                    report.get("provider_uuid"),
                    start_date=start_date,
                    end_date=end_date,
                    manifest_id=report.get("manifest_id"),
                    queue_name=queue_name,
                    tracing_id=tracing_id,
                ).apply_async(queue=queue_name or UPDATE_SUMMARY_TABLES_QUEUE)


@celery_app.task(name="masu.processor.tasks.update_summary_tables", queue=UPDATE_SUMMARY_TABLES_QUEUE)  # noqa: C901
def update_summary_tables(  # noqa: C901
    schema_name,
    provider,
    provider_uuid,
    start_date,
    end_date=None,
    manifest_id=None,
    queue_name=None,
    synchronous=False,
    tracing_id=None,
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
    worker_stats.REPORT_SUMMARY_ATTEMPTS_COUNTER.labels(provider_type=provider).inc()
    task_name = "masu.processor.tasks.update_summary_tables"
    cache_args = [schema_name, provider]

    if not synchronous:
        worker_cache = WorkerCache()
        if worker_cache.single_task_is_running(task_name, cache_args):
            msg = f"Task {task_name} already running for {cache_args}. Requeuing."
            LOG.info(log_json(tracing_id, msg))
            update_summary_tables.s(
                schema_name,
                provider,
                provider_uuid,
                start_date,
                end_date=end_date,
                manifest_id=manifest_id,
                queue_name=queue_name,
                tracing_id=tracing_id,
            ).apply_async(queue=queue_name or UPDATE_SUMMARY_TABLES_QUEUE)
            return
        worker_cache.lock_single_task(task_name, cache_args, timeout=3600)

    stmt = (
        f"update_summary_tables called with args: "
        f" schema_name: {schema_name}, "
        f" provider: {provider}, "
        f" start_date: {start_date}, "
        f" end_date: {end_date}, "
        f" manifest_id: {manifest_id}, "
        f" tracing_id: {tracing_id}"
    )
    LOG.info(log_json(tracing_id, stmt))

    try:
        updater = ReportSummaryUpdater(schema_name, provider_uuid, manifest_id, tracing_id)
        start_date, end_date = updater.update_daily_tables(start_date, end_date)
        updater.update_summary_tables(start_date, end_date, tracing_id)
    except ReportSummaryUpdaterCloudError as ex:
        LOG.info(
            log_json(tracing_id, f"Failed to correlate OpenShift metrics for provider: {provider_uuid}. Error: {ex}")
        )

    except ReportSummaryUpdaterProviderNotFoundError as pnf_ex:
        LOG.warning(
            log_json(
                tracing_id,
                (
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
    if not provider_uuid:
        refresh_materialized_views.s(
            schema_name, provider, manifest_id=manifest_id, queue_name=queue_name, tracing_id=tracing_id
        ).apply_async(queue=queue_name or REFRESH_MATERIALIZED_VIEWS_QUEUE)
        return

    if enable_trino_processing(provider_uuid, provider, schema_name) and provider in (
        Provider.PROVIDER_AWS,
        Provider.PROVIDER_AWS_LOCAL,
        Provider.PROVIDER_AZURE,
        Provider.PROVIDER_AZURE_LOCAL,
    ):
        cost_model = None
        stmt = (
            f"Markup for {provider} is calculated during summarization. No need to run update_cost_model_costs"
            f" schema_name: {schema_name}, "
            f" provider_uuid: {provider_uuid}"
        )
        LOG.info(log_json(tracing_id, stmt))
    else:
        with CostModelDBAccessor(schema_name, provider_uuid) as cost_model_accessor:
            cost_model = cost_model_accessor.cost_model

    if cost_model is not None:
        linked_tasks = update_cost_model_costs.s(
            schema_name, provider_uuid, start_date, end_date, tracing_id=tracing_id
        ).set(queue=queue_name or UPDATE_COST_MODEL_COSTS_QUEUE) | refresh_materialized_views.si(
            schema_name, provider, provider_uuid=provider_uuid, manifest_id=manifest_id, tracing_id=tracing_id
        ).set(
            queue=queue_name or REFRESH_MATERIALIZED_VIEWS_QUEUE
        )
    else:
        stmt = f"update_cost_model_costs skipped. schema_name: {schema_name}, provider_uuid: {provider_uuid}"
        LOG.info(log_json(tracing_id, stmt))
        linked_tasks = refresh_materialized_views.s(
            schema_name, provider, provider_uuid=provider_uuid, manifest_id=manifest_id, tracing_id=tracing_id
        ).set(queue=queue_name or REFRESH_MATERIALIZED_VIEWS_QUEUE)

    chain(linked_tasks).apply_async()
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
    schema_name, provider_uuid, start_date=None, end_date=None, queue_name=None, synchronous=False, tracing_id=None
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
            LOG.info(log_json(tracing_id, msg))
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
        worker_cache.lock_single_task(task_name, cache_args, timeout=600)

    worker_stats.COST_MODEL_COST_UPDATE_ATTEMPTS_COUNTER.inc()

    stmt = (
        f"update_cost_model_costs called with args:\n"
        f" schema_name: {schema_name},\n"
        f" provider_uuid: {provider_uuid},\n"
        f" start_date: {start_date},\n"
        f" start_date: {end_date},\n"
        f" tracing_id: {tracing_id}"
    )
    LOG.info(log_json(tracing_id, stmt))

    try:
        updater = CostModelCostUpdater(schema_name, provider_uuid, tracing_id)
        if updater:
            updater.update_cost_model_costs(start_date, end_date)
    except Exception as ex:
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)
        raise ex

    if not synchronous:
        worker_cache.release_single_task(task_name, cache_args)


# fmt: off
@celery_app.task(  # noqa: C901
    name="masu.processor.tasks.refresh_materialized_views", queue=REFRESH_MATERIALIZED_VIEWS_QUEUE
)
# fmt: on
def refresh_materialized_views(  # noqa: C901
    schema_name, provider_type, manifest_id=None, provider_uuid=None, synchronous=False, queue_name=None,
    tracing_id=None
):
    """Refresh the database's materialized views for reporting."""
    task_name = "masu.processor.tasks.refresh_materialized_views"
    cache_args = [schema_name, provider_type]
    if not synchronous:
        worker_cache = WorkerCache()
        if worker_cache.single_task_is_running(task_name, cache_args):
            msg = f"Task {task_name} already running for {cache_args}. Requeuing."
            LOG.info(log_json(tracing_id, msg))
            refresh_materialized_views.s(
                schema_name,
                provider_type,
                manifest_id=manifest_id,
                provider_uuid=provider_uuid,
                synchronous=synchronous,
                queue_name=queue_name,
                tracing_id=tracing_id
            ).apply_async(queue=queue_name or REFRESH_MATERIALIZED_VIEWS_QUEUE)
            return
        worker_cache.lock_single_task(task_name, cache_args, timeout=600)
    materialized_views = ()
    try:
        with schema_context(schema_name):
            for view in materialized_views:
                table_name = view._meta.db_table
                with connection.cursor() as cursor:
                    cursor.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {table_name}")
                    LOG.info(log_json(tracing_id, f"Refreshed {table_name}."))

        invalidate_view_cache_for_tenant_and_source_type(schema_name, provider_type)

        if provider_uuid:
            ProviderDBAccessor(provider_uuid).set_data_updated_timestamp()
        if manifest_id:
            # Processing for this monifest should be complete after this step
            with ReportManifestDBAccessor() as manifest_accessor:
                manifest = manifest_accessor.get_manifest_by_id(manifest_id)
                manifest_accessor.mark_manifest_as_completed(manifest)
    except Exception as ex:
        if not synchronous:
            worker_cache.release_single_task(task_name, cache_args)
        raise ex

    if not synchronous:
        worker_cache.release_single_task(task_name, cache_args)


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
    """ Remove stale tenants from the tenant api """
    table_sql = """
        SELECT c.schema_name
        FROM api_customer c
        JOIN api_tenant t
            ON c.schema_name = t.schema_name
        LEFT JOIN api_sources s
            ON c.account_id = s.account_id
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
