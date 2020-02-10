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
# pylint: disable=too-many-arguments, too-many-function-args
# disabled module-wide due to current state of task signature.
# we expect this situation to be temporary as we iterate on these details.
import datetime
import os

from celery import chain
from celery.utils.log import get_task_logger
from dateutil import parser
from django.db import connection
from tenant_schemas.utils import schema_context

import masu.prometheus_stats as worker_stats
from api.provider.models import Provider
from koku.celery import app
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.date_accessor import DateAccessor
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor._tasks.remove_expired import _remove_expired_data
from masu.processor._tasks.remove_expired import _remove_expired_line_items
from masu.processor.report_charge_updater import ReportChargeUpdater
from masu.processor.report_processor import ReportProcessorError
from masu.processor.report_summary_updater import ReportSummaryUpdater
from reporting.models import AWS_MATERIALIZED_VIEWS

LOG = get_task_logger(__name__)


# pylint: disable=too-many-locals
@app.task(name="masu.processor.tasks.get_report_files", queue_name="download", bind=True)
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
    month = parser.parse(report_month)
    reports = _get_report_files(
        self, customer_name, authentication, billing_source, provider_type, provider_uuid, month
    )

    try:
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
        for report_dict in reports:
            manifest_id = report_dict.get("manifest_id")
            file_name = os.path.basename(report_dict.get("file"))
            with ReportStatsDBAccessor(file_name, manifest_id) as stats:
                started_date = stats.get_last_started_datetime()
                completed_date = stats.get_last_completed_datetime()

            # Skip processing if already in progress.
            if started_date and not completed_date:
                expired_start_date = started_date + datetime.timedelta(hours=2)
                if DateAccessor().today_with_timezone("UTC") < expired_start_date:
                    LOG.info(
                        "Skipping processing task for %s since it was started at: %s.", file_name, str(started_date)
                    )
                    continue

            # Skip processing if complete.
            if started_date and completed_date:
                LOG.info(
                    "Skipping processing task for %s. Started on: %s and completed on: %s.",
                    file_name,
                    str(started_date),
                    str(completed_date),
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
            worker_stats.PROCESS_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()
            _process_report_file(schema_name, provider_type, provider_uuid, report_dict)
            report_meta = {}
            known_manifest_ids = [report.get("manifest_id") for report in reports_to_summarize]
            if report_dict.get("manifest_id") not in known_manifest_ids:
                report_meta["schema_name"] = schema_name
                report_meta["provider_type"] = provider_type
                report_meta["provider_uuid"] = provider_uuid
                report_meta["manifest_id"] = report_dict.get("manifest_id")
                reports_to_summarize.append(report_meta)
    except ReportProcessorError as processing_error:
        worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
        LOG.error(str(processing_error))
        raise processing_error

    return reports_to_summarize


@app.task(name="masu.processor.tasks.remove_expired_data", queue_name="remove_expired")
def remove_expired_data(schema_name, provider, simulate, provider_uuid=None):
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
        f" provider_uuid: {provider_uuid}"
    )
    LOG.info(stmt)
    _remove_expired_data(schema_name, provider, simulate, provider_uuid)


@app.task(name="masu.processor.tasks.remove_expired_line_items", queue_name="remove_expired_line_items")
def remove_expired_line_items(schema_name, provider, simulate, provider_uuid=None):
    """
    Remove expired line item data.

    Args:
        schema_name (String) db schema name
        provider    (String) provider type
        simulate    (Boolean) Simulate report data removal

    Returns:
        None

    """
    stmt = (
        f"remove_expired_line_items called with args:\n"
        f" schema_name: {schema_name},\n"
        f" provider: {provider},\n"
        f" simulate: {simulate},\n"
        f" provider_uuid: {provider_uuid}"
    )
    LOG.info(stmt)
    _remove_expired_line_items(schema_name, provider, simulate, provider_uuid)


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
    if updater.manifest_is_ready():
        start_date, end_date = updater.update_daily_tables(start_date, end_date)
        updater.update_summary_tables(start_date, end_date)
    if provider_uuid:
        chain(
            update_charge_info.s(schema_name, provider_uuid, start_date, end_date),
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


@app.task(name="masu.processor.tasks.update_charge_info", queue_name="reporting")
def update_charge_info(schema_name, provider_uuid, start_date=None, end_date=None):
    """Update usage charge information.

    Args:
        schema_name (str) The DB schema name.
        provider_uuid (str) The provider uuid.
        start_date (str, Optional) - Start date of range to update derived cost.
        end_date (str, Optional) - End date of range to update derived cost.

    Returns
        None

    """
    worker_stats.CHARGE_UPDATE_ATTEMPTS_COUNTER.inc()

    stmt = (
        f"update_charge_info called with args:\n" f" schema_name: {schema_name},\n" f" provider_uuid: {provider_uuid}"
    )
    LOG.info(stmt)

    updater = ReportChargeUpdater(schema_name, provider_uuid)
    updater.update_charge_info(start_date, end_date)


@app.task(name="masu.processor.tasks.refresh_materialized_views", queue_name="reporting")
def refresh_materialized_views(schema_name, provider_type, manifest_id=None):
    """Refresh the database's materialized views for reporting."""
    materialized_views = ()
    if provider_type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
        materialized_views = AWS_MATERIALIZED_VIEWS
    with schema_context(schema_name):
        for view in materialized_views:
            table_name = view._meta.db_table
            with connection.cursor() as cursor:
                cursor.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {table_name}")
                LOG.info(f"Refreshed {table_name}.")

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
