#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Asynchronous tasks."""
import datetime
import json
import os
import time
from decimal import Decimal
from decimal import InvalidOperation

from botocore.exceptions import ClientError
from celery import chain
from celery.utils.log import get_task_logger
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
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from koku.celery import app
from koku.middleware import KokuTenantMiddleware
from masu.config import Config
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.ocp.ocp_report_downloader import REPORT_TYPES
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor._tasks.remove_expired import _remove_expired_data
from masu.processor.cost_model_cost_updater import CostModelCostUpdater
from masu.processor.report_processor import ReportProcessorDBError
from masu.processor.report_processor import ReportProcessorError
from masu.processor.report_summary_updater import ReportSummaryUpdater
from masu.processor.worker_cache import WorkerCache
from masu.util.aws.common import aws_post_processor
from masu.util.aws.common import convert_csv_to_parquet
from masu.util.aws.common import get_file_keys_from_s3_with_manifest_id
from masu.util.aws.common import remove_files_not_in_set_from_s3_bucket
from masu.util.common import get_column_converters
from masu.util.common import get_path_prefix
from reporting.models import AWS_MATERIALIZED_VIEWS
from reporting.models import AZURE_MATERIALIZED_VIEWS
from reporting.models import OCP_MATERIALIZED_VIEWS
from reporting.models import OCP_ON_AWS_MATERIALIZED_VIEWS
from reporting.models import OCP_ON_AZURE_MATERIALIZED_VIEWS
from reporting.models import OCP_ON_INFRASTRUCTURE_MATERIALIZED_VIEWS

LOG = get_task_logger(__name__)


def record_all_manifest_files(manifest_id, report_files):
    """Store all report file names for manifest ID."""
    for report in report_files:
        try:
            with ReportStatsDBAccessor(report, manifest_id):
                LOG.debug(f"Logging {report} for manifest ID: {manifest_id}")
        except IntegrityError:
            # OCP records the entire file list for a new manifest when the listener
            # recieves a payload.  With multiple listeners it is possilbe for
            # two listeners to recieve a report file for the same manifest at
            # roughly the same time.  In that case the report file may already
            # exist and an IntegrityError would be thrown.
            LOG.debug(f"Report {report} has already been recorded.")


def record_report_status(manifest_id, file_name, request_id, context={}):
    """
    Creates initial report status database entry for new report files.

    If a report has already been downloaded from the ingress service
    there is a chance that processing has already been complete.  The
    function returns the last completed date time to determine if the
    report processing should continue in extract_payload.

    Args:
        manifest_id (Integer): Manifest Identifier.
        file_name (String): Report file name
        request_id (String): Identifier associated with the payload
        context (Dict): Context for logging (account, etc)

    Returns:
        DateTime - Last completed date time for a given report file.

    """
    already_processed = False
    with ReportStatsDBAccessor(file_name, manifest_id) as db_accessor:
        already_processed = db_accessor.get_last_completed_datetime()
        if already_processed:
            msg = f"Report {file_name} has already been processed."
            LOG.info(log_json(request_id, msg, context))
        else:
            msg = f"Recording stats entry for {file_name}"
            LOG.info(log_json(request_id, msg, context))
    return already_processed


# pylint: disable=too-many-locals
@app.task(name="masu.processor.tasks.get_report_files", queue_name="download", bind=True)
def get_report_files(
    self,
    customer_name,
    authentication,
    billing_source,
    provider_type,
    schema_name,
    provider_uuid,
    report_month,
    report_context,
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
        WorkerCache().add_task_to_cache(cache_key)

        report_dict = _get_report_files(
            self,
            customer_name,
            authentication,
            billing_source,
            provider_type,
            provider_uuid,
            month,
            cache_key,
            report_context,
        )

        stmt = (
            f"Reports to be processed:\n"
            f" schema_name: {customer_name}\n"
            f" provider: {provider_type}\n"
            f" provider_uuid: {provider_uuid}\n"
        )
        if report_dict:
            stmt += f" file: {report_dict['file']}"
            LOG.info(stmt)
        else:
            WorkerCache().remove_task_from_cache(cache_key)
            return None

        try:
            stmt = (
                f"Processing starting:\n"
                f" schema_name: {customer_name}\n"
                f" provider: {provider_type}\n"
                f" provider_uuid: {provider_uuid}\n"
                f' file: {report_dict.get("file")}'
            )
            LOG.info(stmt)
            worker_stats.PROCESS_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()

            _process_report_file(schema_name, provider_type, report_dict)

            report_meta = {
                "schema_name": schema_name,
                "provider_type": provider_type,
                "provider_uuid": provider_uuid,
                "manifest_id": report_dict.get("manifest_id"),
            }

        except (ReportProcessorError, ReportProcessorDBError) as processing_error:
            worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
            LOG.error(str(processing_error))
            WorkerCache().remove_task_from_cache(cache_key)
            raise processing_error

        WorkerCache().remove_task_from_cache(cache_key)
        start_date = report_dict.get("start_date")
        manifest_id = report_dict.get("manifest_id")
        if start_date:
            start_date_str = start_date.strftime("%Y-%m-%d")
            convert_to_parquet.delay(
                self.request.id,
                schema_name[4:],
                provider_uuid,
                provider_type,
                start_date_str,
                manifest_id,
                [report_context.get("local_file")],
            )
        return report_meta
    except Exception as err:
        worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
        LOG.error(str(err))
        WorkerCache().remove_task_from_cache(cache_key)


@app.task(name="masu.processor.tasks.remove_expired_data", queue_name="remove_expired")
def remove_expired_data(schema_name, provider, simulate, provider_uuid=None, line_items_only=False):
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
        f" line_items_only: {line_items_only}",
    )
    LOG.info(stmt)
    _remove_expired_data(schema_name, provider, simulate, provider_uuid, line_items_only)
    if not line_items_only:
        refresh_materialized_views.delay(schema_name, provider, provider_uuid=provider_uuid)


@app.task(name="masu.processor.tasks.summarize_reports", queue_name="process")
def summarize_reports(reports_to_summarize):
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
                start_date = DateAccessor().today() - datetime.timedelta(days=2)
                start_date = start_date.strftime("%Y-%m-%d")
                end_date = DateAccessor().today().strftime("%Y-%m-%d")
                LOG.info("report to summarize: %s", str(report))
                update_summary_tables.delay(
                    report.get("schema_name"),
                    report.get("provider_type"),
                    report.get("provider_uuid"),
                    start_date=start_date,
                    end_date=end_date,
                    manifest_id=report.get("manifest_id"),
                )


@app.task(name="masu.processor.tasks.update_summary_tables", queue_name="reporting")
def update_summary_tables(schema_name, provider, provider_uuid, start_date, end_date=None, manifest_id=None):
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

    stmt = (
        f"update_summary_tables called with args:\n"
        f" schema_name: {schema_name},\n"
        f" provider: {provider},\n"
        f" start_date: {start_date},\n"
        f" end_date: {end_date},\n"
        f" manifest_id: {manifest_id}"
    )
    LOG.info(stmt)

    updater = ReportSummaryUpdater(schema_name, provider_uuid, manifest_id)

    start_date, end_date = updater.update_daily_tables(start_date, end_date)
    updater.update_summary_tables(start_date, end_date)

    if not provider_uuid:
        refresh_materialized_views.delay(schema_name, provider, manifest_id=manifest_id)
        return

    with CostModelDBAccessor(schema_name, provider_uuid) as cost_model_accessor:
        cost_model = cost_model_accessor.cost_model

    if cost_model is not None:
        linked_tasks = update_cost_model_costs.s(
            schema_name, provider_uuid, start_date, end_date
        ) | refresh_materialized_views.si(schema_name, provider, provider_uuid=provider_uuid, manifest_id=manifest_id)
    else:
        stmt = (
            f"\n update_cost_model_costs skipped. No cost model available for \n"
            f" schema_name: {schema_name},\n"
            f" provider_uuid: {provider_uuid}"
        )
        LOG.info(stmt)
        linked_tasks = refresh_materialized_views.s(
            schema_name, provider, provider_uuid=provider_uuid, manifest_id=manifest_id
        )

    dh = DateHelper(utc=True)
    prev_month_start_day = dh.last_month_start.replace(tzinfo=None)
    start_date_obj = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    if manifest_id and (start_date_obj <= prev_month_start_day):
        # We want make sure that the manifest_id is not none, because
        # we only want to call the delete line items after the summarize_reports
        # task above
        simulate = False
        line_items_only = True

        linked_tasks |= remove_expired_data.si(schema_name, provider, simulate, provider_uuid, line_items_only)

    chain(linked_tasks).apply_async()


@app.task(name="masu.processor.tasks.update_all_summary_tables", queue_name="reporting")
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
            update_summary_tables.delay(schema_name, provider, provider_uuid, str(start_date), end_date)
    except AccountsAccessorError as error:
        LOG.error("Unable to get accounts. Error: %s", str(error))


@app.task(name="masu.processor.tasks.update_cost_model_costs", queue_name="reporting")
def update_cost_model_costs(
    schema_name, provider_uuid, start_date=None, end_date=None, provider_type=None, synchronous=False
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
        while worker_cache.single_task_is_running(task_name, cache_args):
            time.sleep(5)
        worker_cache.lock_single_task(task_name, cache_args, timeout=300)

    worker_stats.COST_MODEL_COST_UPDATE_ATTEMPTS_COUNTER.inc()

    stmt = (
        f"update_cost_model_costs called with args:\n"
        f" schema_name: {schema_name},\n"
        f" provider_uuid: {provider_uuid}"
    )
    LOG.info(stmt)

    updater = CostModelCostUpdater(schema_name, provider_uuid)
    if updater:
        updater.update_cost_model_costs(start_date, end_date)

    if not synchronous:
        worker_cache.release_single_task(task_name, cache_args)


@app.task(name="masu.processor.tasks.refresh_materialized_views", queue_name="reporting")
def refresh_materialized_views(schema_name, provider_type, manifest_id=None, provider_uuid=None, synchronous=False):
    """Refresh the database's materialized views for reporting."""
    task_name = "masu.processor.tasks.refresh_materialized_views"
    cache_args = [schema_name]
    if not synchronous:
        worker_cache = WorkerCache()
        while worker_cache.single_task_is_running(task_name, cache_args):
            time.sleep(5)

        worker_cache.lock_single_task(task_name, cache_args)
    materialized_views = ()
    if provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
        materialized_views = (
            AWS_MATERIALIZED_VIEWS + OCP_ON_AWS_MATERIALIZED_VIEWS + OCP_ON_INFRASTRUCTURE_MATERIALIZED_VIEWS
        )
    elif provider_type in (Provider.PROVIDER_OCP):
        materialized_views = (
            OCP_MATERIALIZED_VIEWS
            + OCP_ON_AWS_MATERIALIZED_VIEWS
            + OCP_ON_AZURE_MATERIALIZED_VIEWS
            + OCP_ON_INFRASTRUCTURE_MATERIALIZED_VIEWS
        )
    elif provider_type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
        materialized_views = (
            AZURE_MATERIALIZED_VIEWS + OCP_ON_AZURE_MATERIALIZED_VIEWS + OCP_ON_INFRASTRUCTURE_MATERIALIZED_VIEWS
        )

    with schema_context(schema_name):
        for view in materialized_views:
            table_name = view._meta.db_table
            with connection.cursor() as cursor:
                cursor.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {table_name}")
                LOG.info(f"Refreshed {table_name}.")

    invalidate_view_cache_for_tenant_and_source_type(schema_name, provider_type)

    if provider_uuid:
        ProviderDBAccessor(provider_uuid).set_data_updated_timestamp()
    if manifest_id:
        # Processing for this monifest should be complete after this step
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(manifest_id)
            manifest_accessor.mark_manifest_as_completed(manifest)

    if not synchronous:
        worker_cache.release_single_task(task_name, cache_args)


@app.task(name="masu.processor.tasks.vacuum_schema", queue_name="reporting")
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
@app.task(name="masu.processor.tasks.autovacuum_tune_schema", queue_name="reporting")
def autovacuum_tune_schema(schema_name):  # noqa: C901
    """Set the autovacuum table settings based on table size for the specified schema."""
    table_sql = """
SELECT s.relname as "table_name",
       s.n_live_tup,
       coalesce(table_options.options, '{}'::jsonb) as "options"
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


@app.task(
    name="masu.celery.tasks.convert_to_parquet",
    queue_name="reporting",
    autoretry_for=(ClientError,),
    max_retries=10,
    retry_backoff=10,
)
def convert_to_parquet(  # noqa: C901
    request_id, account, provider_uuid, provider_type, start_date, manifest_id, files=[], context={}
):
    """
    Convert archived CSV data from our S3 bucket for a given provider to Parquet.

    This function chiefly follows the download of a providers data.

    This task is defined to attempt up to 10 retries using exponential backoff
    starting with a 10-second delay. This is intended to allow graceful handling
    of temporary AWS S3 connectivity issues because it is relatively important
    for us to convert the archived data.

    Args:
        request_id (str): The associated request id (ingress or celery task id)
        account (str): The account string
        provider_uuid (UUID): The provider UUID
        start_date (str): The report start time (YYYY-mm-dd)
        manifest_id (str): The identifier for the report manifest
        context (dict): A context object for logging

    """
    if not context:
        context = {"account": account, "provider_uuid": provider_uuid}

    if not settings.ENABLE_PARQUET_PROCESSING:
        msg = "Skipping convert_to_parquet. Parquet processing is disabled."
        LOG.info(log_json(request_id, msg, context))
        return

    if not request_id or not account or not provider_uuid:
        if not request_id:
            message = "missing required argument: request_id"
            LOG.error(message)
        if not account:
            message = "missing required argument: account"
            LOG.error(message)
        if not provider_uuid:
            message = "missing required argument: provider_uuid"
            LOG.error(message)
        if not provider_type:
            message = "missing required argument: provider_type"
            LOG.error(message)
        return

    if not start_date:
        msg = "Parquet processing is enabled, but no start_date was given for processing."
        LOG.warn(log_json(request_id, msg, context))
        return

    try:
        cost_date = parser.parse(start_date)
    except ValueError:
        msg = "Parquet processing is enabled, but the start_date was not a valid date string ISO 8601 format."
        LOG.warn(log_json(request_id, msg, context))
        return

    s3_csv_path = get_path_prefix(account, provider_uuid, cost_date, Config.CSV_DATA_TYPE)
    local_path = f"{Config.TMP_DIR}/{account}/{provider_uuid}"
    s3_parquet_path = get_path_prefix(account, provider_uuid, cost_date, Config.PARQUET_DATA_TYPE)

    if not files:
        file_keys = get_file_keys_from_s3_with_manifest_id(request_id, s3_csv_path, manifest_id, context)
        files = [os.path.basename(file_key) for file_key in file_keys]
        if not files:
            msg = "Parquet processing is enabled, but no files to process."
            LOG.info(log_json(request_id, msg, context))
            return

    post_processor = None
    # OCP data is daily chunked report files.
    # AWS and Azure are monthly reports. Previous reports should be removed so data isn't duplicated
    if provider_type != Provider.PROVIDER_OCP:
        remove_files_not_in_set_from_s3_bucket(request_id, s3_parquet_path, manifest_id, context)

    if provider_type in [Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL]:
        post_processor = aws_post_processor

    failed_conversion = []
    for csv_filename in files:
        kwargs = {}
        parquet_path = s3_parquet_path
        parquet_report_type = None
        if provider_type == Provider.PROVIDER_OCP:
            for report_type in REPORT_TYPES.keys():
                if report_type in csv_filename:
                    parquet_path = f"{s3_parquet_path}/{report_type}"
                    kwargs["report_type"] = report_type
                    parquet_report_type = report_type
                    break
        converters = get_column_converters(provider_type, **kwargs)
        result = convert_csv_to_parquet(
            request_id,
            s3_csv_path,
            parquet_path,
            local_path,
            manifest_id,
            csv_filename,
            converters,
            post_processor,
            context,
            parquet_report_type,
        )
        if not result:
            failed_conversion.append(csv_filename)

    if failed_conversion:
        msg = f"Failed to convert the following files to parquet:{','.join(failed_conversion)}."
        LOG.warn(log_json(request_id, msg, context))
        return


@app.task(name="masu.processor.tasks.remove_stale_tenants", queue_name="remove_stale_tenants")
def remove_stale_tenants():
    """ Remove stale tenants from the tenant api """
    table_sql = """
        SELECT schema_name
        FROM api_customer c
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
