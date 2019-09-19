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

from celery.utils.log import get_task_logger

import masu.prometheus_stats as worker_stats
from koku.celery import CELERY as celery
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.accounts_accessor import (AccountsAccessor, AccountsAccessorError)
from masu.external.date_accessor import DateAccessor
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor._tasks.remove_expired import _remove_expired_data
from masu.processor.report_charge_updater import ReportChargeUpdater
from masu.processor.report_processor import ReportProcessorError
from masu.processor.report_summary_updater import ReportSummaryUpdater

LOG = get_task_logger(__name__)


# pylint: disable=too-many-locals
@celery.task(name='masu.processor.tasks.get_report_files', queue_name='download')
def get_report_files(customer_name,
                     authentication,
                     billing_source,
                     provider_type,
                     schema_name,
                     provider_uuid):
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
    reports = _get_report_files(customer_name,
                                authentication,
                                billing_source,
                                provider_type,
                                provider_uuid)

    try:
        LOG.info('Reports to be processed: %s', str(reports))
        reports_to_summarize = []
        for report_dict in reports:
            manifest_id = report_dict.get('manifest_id')
            file_name = os.path.basename(report_dict.get('file'))
            with ReportStatsDBAccessor(file_name, manifest_id) as stats:
                started_date = stats.get_last_started_datetime()
                completed_date = stats.get_last_completed_datetime()

            # Skip processing if already in progress.
            if started_date and not completed_date:
                expired_start_date = started_date + datetime.timedelta(hours=2)
                if DateAccessor().today_with_timezone('UTC') < expired_start_date:
                    LOG.info('Skipping processing task for %s since it was started at: %s.',
                             file_name, str(started_date))
                    continue

            # Skip processing if complete.
            if started_date and completed_date:
                LOG.info('Skipping processing task for %s. Started on: %s and completed on: %s.',
                         file_name, str(started_date), str(completed_date))
                continue

            LOG.info('Processing starting - schema_name: %s, provider_uuid: %s, File: %s',
                     schema_name, provider_uuid, report_dict.get('file'))
            worker_stats.PROCESS_REPORT_ATTEMPTS_COUNTER.labels(provider_type=provider_type).inc()
            _process_report_file(schema_name,
                                 provider_type,
                                 provider_uuid,
                                 report_dict)
            report_meta = {}
            known_manifest_ids = [report.get('manifest_id') for report in reports_to_summarize]
            if report_dict.get('manifest_id') not in known_manifest_ids:
                report_meta['schema_name'] = schema_name
                report_meta['provider_type'] = provider_type
                report_meta['provider_uuid'] = provider_uuid
                report_meta['manifest_id'] = report_dict.get('manifest_id')
                reports_to_summarize.append(report_meta)
    except ReportProcessorError as processing_error:
        worker_stats.PROCESS_REPORT_ERROR_COUNTER.labels(provider_type=provider_type).inc()
        LOG.error(str(processing_error))

    return reports_to_summarize


@celery.task(name='masu.processor.tasks.remove_expired_data', queue_name='remove_expired')
def remove_expired_data(schema_name, provider, simulate, provider_id=None):
    """
    Remove expired report data.

    Args:
        schema_name (String) db schema name
        provider    (String) provider type
        simulate    (Boolean) Simulate report data removal

    Returns:
        None

    """
    stmt = (f'remove_expired_data called with args:\n'
            f' schema_name: {schema_name},\n'
            f' provider: {provider},\n'
            f' simulate: {simulate},\n'
            f' provider_id: {provider_id}')
    LOG.info(stmt)
    _remove_expired_data(schema_name, provider, simulate, provider_id)


@celery.task(name='masu.processor.tasks.summarize_reports',
             queue_name='process')
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
        start_date = start_date.strftime('%Y-%m-%d')
        end_date = DateAccessor().today().strftime('%Y-%m-%d')
        LOG.info('report to summarize: %s', str(report))
        update_summary_tables.delay(
            report.get('schema_name'),
            report.get('provider_type'),
            report.get('provider_uuid'),
            start_date=start_date,
            end_date=end_date,
            manifest_id=report.get('manifest_id')
        )


@celery.task(name='masu.processor.tasks.update_summary_tables',
             queue_name='reporting')
def update_summary_tables(schema_name, provider, provider_uuid, start_date, end_date=None,
                          manifest_id=None):
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

    stmt = (f'update_summary_tables called with args:\n'
            f' schema_name: {schema_name},\n'
            f' provider: {provider},\n'
            f' start_date: {start_date},\n'
            f' end_date: {end_date},\n'
            f' manifest_id: {manifest_id}')
    LOG.info(stmt)

    updater = ReportSummaryUpdater(schema_name, provider_uuid, manifest_id)
    if updater.manifest_is_ready():
        start_date, end_date = updater.update_daily_tables(start_date, end_date)
        updater.update_summary_tables(start_date, end_date)

    if provider_uuid:
        update_charge_info.apply_async(
            args=(
                schema_name,
                provider_uuid,
                start_date,
                end_date),
            link=update_cost_summary_table.si(
                schema_name,
                provider_uuid,
                start_date,
                end_date,
                manifest_id))


@celery.task(name='masu.processor.tasks.update_all_summary_tables',
             queue_name='reporting')
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
            LOG.info('Gathering data for account=%s.', account)
            schema_name = account.get('schema_name')
            provider = account.get('provider_type')
            provider_uuid = account.get('provider_uuid')
            update_summary_tables.delay(schema_name, provider,
                                        provider_uuid, str(start_date), end_date)
    except AccountsAccessorError as error:
        LOG.error('Unable to get accounts. Error: %s', str(error))


@celery.task(name='masu.processor.tasks.update_charge_info',
             queue_name='reporting')
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

    stmt = (f'update_charge_info called with args:\n'
            f' schema_name: {schema_name},\n'
            f' provider_uuid: {provider_uuid}')
    LOG.info(stmt)

    updater = ReportChargeUpdater(schema_name, provider_uuid)
    updater.update_charge_info(start_date, end_date)


@celery.task(name='masu.processor.tasks.update_cost_summary_table',
             queue_name='reporting')
def update_cost_summary_table(schema_name, provider_uuid, start_date,
                              end_date=None, manifest_id=None):
    """Update derived costs summary table.

    Args:
        schema_name (str) The DB schema name.
        provider_uuid (str) The provider uuid.
        manifest_id (str) The manifest id.
        start_date (str, Optional) - Start date of range to update derived cost.
        end_date (str, Optional) - End date of range to update derived cost.

    Returns:
        None

    """
    worker_stats.COST_SUMMARY_ATTEMPTS_COUNTER.inc()

    stmt = (f'update_cost_summary_table called with args:\n'
            f' schema_name: {schema_name},\n'
            f' provider_uuid: {provider_uuid}\n'
            f' manifest_id: {manifest_id}')
    LOG.info(stmt)

    updater = ReportSummaryUpdater(schema_name, provider_uuid, manifest_id)
    updater.update_cost_summary_table(start_date, end_date)
