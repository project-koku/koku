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
from decimal import Decimal
from decimal import InvalidOperation

from botocore.exceptions import ClientError
from celery import chain
from celery.utils.log import get_task_logger
from dateutil import parser
from django.conf import settings
from django.db import connection
from django.db import transaction
from tenant_schemas.utils import schema_context

import masu.prometheus_stats as worker_stats
from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from koku.celery import app
from masu.config import Config
from masu.database.cost_model_db_accessor import CostModelDBAccessor
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
from masu.util.aws.common import convert_csv_to_parquet
from masu.util.aws.common import get_file_keys_from_s3_with_manifest_id
from masu.util.aws.common import remove_files_not_in_set_from_s3_bucket
from masu.util.common import get_path_prefix
from reporting.models import AWS_MATERIALIZED_VIEWS
from reporting.models import AZURE_MATERIALIZED_VIEWS
from reporting.models import OCP_MATERIALIZED_VIEWS
from reporting.models import OCP_ON_AWS_MATERIALIZED_VIEWS
from reporting.models import OCP_ON_AZURE_MATERIALIZED_VIEWS
from reporting.models import OCP_ON_INFRASTRUCTURE_MATERIALIZED_VIEWS

LOG = get_task_logger(__name__)


@app.task(name="masu.processor.tasks.get_report_files", queue_name="download", bind=True)  # noqa: C901
def get_report_files(
    self, customer_name, authentication, billing_source, provider_type, schema_name, provider_uuid, report_month
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
    worker_stats.GET_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()
    month = report_month
    if isinstance(report_month, str):
        month = parser.parse(report_month)

    cache_key = f"{provider_uuid}:{month}"
    reports = _get_report_files(
        self, customer_name, authentication, billing_source, provider_type, provider_uuid, month, cache_key
    )

    stmt = (
        f"Reports to be processed:\n"
        f" schema_name: {customer_name}\n"
        f" provider: {provider_type}\n"
        f" provider_uuid: {provider_uuid}\n"
    )
    for report in reports:
        stmt += " file: " + str(report["file"]) + "\n"
    LOG.info(stmt[:-1])
    reports_to_summarize = []
    start_date = None

    for report_dict in reports:
        with transaction.atomic():
            try:
                manifest_id = report_dict.get("manifest_id")
                file_name = os.path.basename(report_dict.get("file"))
                with ReportStatsDBAccessor(file_name, manifest_id) as stats:
                    started_date = stats.get_last_started_datetime()
                    completed_date = stats.get_last_completed_datetime()

                # Skip processing if already in progress.
                if started_date and not completed_date:
                    expired_start_date = started_date + datetime.timedelta(
                        hours=Config.REPORT_PROCESSING_TIMEOUT_HOURS
                    )
                    if DateAccessor().today_with_timezone("UTC") < expired_start_date:
                        LOG.info(
                            "Skipping processing task for %s since it was started at: %s.",
                            file_name,
                            str(started_date),
                        )
                        continue

                stmt = (
                    f"Processing starting:\n"
                    f" schema_name: {customer_name}\n"
                    f" provider: {provider_type}\n"
                    f" provider_uuid: {provider_uuid}\n"
                    f' file: {report_dict.get("file")}'
                )
                LOG.info(stmt)
                if not start_date:
                    start_date = report_dict.get("start_date")
                worker_stats.PROCESS_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()
                _process_report_file(schema_name, provider_type, provider_uuid, report_dict)
                known_manifest_ids = [report.get("manifest_id") for report in reports_to_summarize]
                if report_dict.get("manifest_id") not in known_manifest_ids:
                    report_meta = {
                        "schema_name": schema_name,
                        "provider_type": provider_type,
                        "provider_uuid": provider_uuid,
                        "manifest_id": report_dict.get("manifest_id"),
                    }
                    reports_to_summarize.append(report_meta)
            except (ReportProcessorError, ReportProcessorDBError) as processing_error:
                worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
                LOG.error(str(processing_error))
                WorkerCache().remove_task_from_cache(cache_key)
                raise processing_error

    WorkerCache().remove_task_from_cache(cache_key)
    if start_date:
        start_date_str = start_date.strftime("%Y-%m-%d")
        convert_to_parquet.delay(
            self.request.id, schema_name[4:], provider_uuid, provider_type, start_date_str, manifest_id
        )

    return reports_to_summarize


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
    refresh_materialized_views.delay(schema_name, provider)


@app.task(name="masu.processor.tasks.summarize_reports", queue_name="process")
def summarize_reports(reports_to_summarize):
    """
    Summarize reports returned from line summary task.

    Args:
        reports_to_summarize (list) list of reports to process

    Returns:
        None

    """
    for report in reports_to_summarize:
        # For day-to-day summarization we choose a small window to
        # cover new data from a window of days.
        # This saves us from re-summarizing unchanged data and cuts down
        # on processing time. There are override mechanisms in the
        # Updater classes for when full-month summarization is
        # required.
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

    if provider_uuid:
        dh = DateHelper(utc=True)
        prev_month_last_day = dh.last_month_end
        start_date_obj = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        prev_month_last_day = prev_month_last_day.replace(tzinfo=None)
        prev_month_last_day = prev_month_last_day.replace(microsecond=0, second=0, minute=0, hour=0, day=1)
        if manifest_id and (start_date_obj <= prev_month_last_day):
            # We want make sure that the manifest_id is not none, because
            # we only want to call the delete line items after the summarize_reports
            # task above
            simulate = False
            line_items_only = True
            chain(
                update_cost_model_costs.s(schema_name, provider_uuid, start_date, end_date),
                refresh_materialized_views.si(schema_name, provider, manifest_id),
                remove_expired_data.si(schema_name, provider, simulate, provider_uuid, line_items_only),
            ).apply_async()
        else:
            chain(
                update_cost_model_costs.s(schema_name, provider_uuid, start_date, end_date),
                refresh_materialized_views.si(schema_name, provider, manifest_id),
            ).apply_async()
    else:
        refresh_materialized_views.delay(schema_name, provider, manifest_id)


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
def update_cost_model_costs(schema_name, provider_uuid, start_date=None, end_date=None):
    """Update usage charge information.

    Args:
        schema_name (str) The DB schema name.
        provider_uuid (str) The provider uuid.
        start_date (str, Optional) - Start date of range to update derived cost.
        end_date (str, Optional) - End date of range to update derived cost.

    Returns
        None

    """
    with CostModelDBAccessor(schema_name, provider_uuid) as cost_model_accessor:
        cost_model = cost_model_accessor.cost_model
    if cost_model is not None:
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
    else:
        stmt = (
            f"\n update_cost_model_costs skipped. No cost model available for \n"
            f" schema_name: {schema_name},\n"
            f" provider_uuid: {provider_uuid}"
        )
        LOG.info(stmt)


@app.task(name="masu.processor.tasks.refresh_materialized_views", queue_name="reporting")
def refresh_materialized_views(schema_name, provider_type, manifest_id=None):
    """Refresh the database's materialized views for reporting."""
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

    if manifest_id:
        # Processing for this monifest should be complete after this step
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(manifest_id)
            manifest_accessor.mark_manifest_as_completed(manifest)


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
@app.task(name="masu.processor.tasks.autovacuum_tune_schema", queue_name="reporting")  # noqa: C901
def autovacuum_tune_schema(schema_name):
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


@app.task(  # noqa: C901
    name="masu.celery.tasks.convert_reports_to_parquet",
    queue_name="reporting",
    autoretry_for=(ClientError,),
    max_retries=10,
    retry_backoff=10,
)
def convert_reports_to_parquet(request_id, reports_to_convert, context={}):
    """
    Convert archived CSV data from our S3 bucket for a given provider to Parquet.

    This function chiefly follows the download of a providers data.

    This task is defined to attempt up to 10 retries using exponential backoff
    starting with a 10-second delay. This is intended to allow graceful handling
    of temporary AWS S3 connectivity issues because it is relatively important
    for us to convert the archived data.

    Args:
        request_id (str): The associated request id (ingress or celery task id)
        reports_to_convert (list(Dict)): The list of report dictionaries
        context (dict): A context object for logging

    """
    if not settings.ENABLE_S3_ARCHIVING:
        msg = "Skipping convert_reports_to_parquet. S3 archiving feature is disabled."
        LOG.info(log_json(request_id, msg, context))
        return

    for report in reports_to_convert:
        LOG.info("report to convert: %s", str(report))
        schema_name = report.get("schema_name")
        provider_uuid = report.get("provider_uuid")
        provider_type = report.get("provider_type")
        manifest_id = report.get("manifest_id")
        start_date = report.get("start_date")

        if start_date and schema_name:
            account = schema_name[4:]
            convert_to_parquet.delay(request_id, account, provider_uuid, provider_type, start_date, manifest_id)


@app.task(  # noqa: C901
    name="masu.celery.tasks.convert_to_parquet",
    queue_name="reporting",
    autoretry_for=(ClientError,),
    max_retries=10,
    retry_backoff=10,
)
def convert_to_parquet(request_id, account, provider_uuid, provider_type, start_date, manifest_id, context={}):
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

    if not settings.ENABLE_S3_ARCHIVING:
        msg = "Skipping convert_to_parquet. S3 archiving feature is disabled."
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
        msg = "S3 archiving feature is enabled, but no start_date was given for processing."
        LOG.warn(log_json(request_id, msg, context))
        return

    try:
        cost_date = parser.parse(start_date)
    except ValueError:
        msg = "S3 archiving feature is enabled, but the start_date was not a valid date string ISO 8601 format."
        LOG.warn(log_json(request_id, msg, context))
        return

    s3_csv_path = get_path_prefix(account, provider_uuid, cost_date, Config.CSV_DATA_TYPE)
    local_path = f"{Config.TMP_DIR}/{account}/{provider_uuid}"
    s3_parquet_path = get_path_prefix(account, provider_uuid, cost_date, Config.PARQUET_DATA_TYPE)

    file_keys = get_file_keys_from_s3_with_manifest_id(request_id, s3_csv_path, manifest_id, context)
    files = [os.path.basename(file_key) for file_key in file_keys]
    if not files:
        msg = "S3 archiving feature is enabled, but no files to process."
        LOG.info(log_json(request_id, msg, context))
        return

    # OCP data is daily chunked report files.
    # AWS and Azure are monthly reports. Previous reports should be removed so data isn't duplicated
    if provider_type != Provider.PROVIDER_OCP:
        remove_files_not_in_set_from_s3_bucket(request_id, s3_parquet_path, manifest_id, context)

    failed_conversion = []
    for csv_filename in files:
        parquet_path = s3_parquet_path
        if provider_type == Provider.PROVIDER_OCP:
            for report_type in REPORT_TYPES.keys():
                if report_type in csv_filename:
                    parquet_path = f"{s3_parquet_path}/{report_type}"
                    break
        result = convert_csv_to_parquet(
            request_id, s3_csv_path, parquet_path, local_path, manifest_id, csv_filename, context
        )
        if not result:
            failed_conversion.append(csv_filename)

    if failed_conversion:
        msg = f"Failed to convert the following files to parquet:{','.join(failed_conversion)}."
        LOG.warn(log_json(request_id, msg, context))
        return
