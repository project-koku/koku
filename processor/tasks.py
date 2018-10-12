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

from masu.celery import celery
from masu.database.report_db_accessor import ReportDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor._tasks.remove_expired import _remove_expired_data

LOG = get_task_logger(__name__)


@celery.task(name='masu.processor.tasks.get_report_files', queue_name='download')
def get_report_files(customer_name,
                     authentication,
                     billing_source,
                     provider_type,
                     schema_name,
                     provider_uuid):
    """
    Task to download a Report.

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
        files (List) List of filenames with full local path.
               Example: ['/var/tmp/masu/my-report-name/aws/my-report-file.csv',
                         '/var/tmp/masu/other-report-name/aws/other-report-file.csv']

    """
    reports = _get_report_files(customer_name,
                                authentication,
                                billing_source,
                                provider_type,
                                provider_uuid)

    # initiate chained async task
    LOG.info('Reports to be processed: %s', str(reports))
    for report_dict in reports:
        manifest_id = report_dict.get('manifest_id')
        file_name = os.path.basename(report_dict.get('file'))
        stats = ReportStatsDBAccessor(file_name, manifest_id)
        started_date = stats.get_last_started_datetime()
        completed_date = stats.get_last_completed_datetime()
        stats.close_session()

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

        result = process_report_file.delay(schema_name, provider_type,
                                           provider_uuid, report_dict)
        LOG.info('Processing task queued - File: %s, Task ID: %s',
                 report_dict.get('file'),
                 str(result))


@celery.task(name='masu.processor.tasks.process_report_file', queue_name='process')
def process_report_file(schema_name, provider, provider_uuid, report_dict):
    """
    Task to process a Report.

    Args:
        schema_name (String) db schema name
        provider    (String) provider type
        provider_uuid (String) provider_uuid
        report_dict (dict) The report data dict from previous task

    Returns:
        None

    """
    _process_report_file(schema_name, provider, provider_uuid, report_dict)
    LOG.info('Queueing update_summary_tables task for %s', schema_name)
    start_date = DateAccessor().today().strftime('%Y-%m-%d')
    update_summary_tables.delay(
        schema_name,
        provider,
        start_date,
        manifest_id=report_dict.get('manifest_id')
    )


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
    stmt = ('remove_expired_data called with args:\n'
            ' schema_name: {},\n'
            ' provider: {},\n'
            ' simulate: {},\n'
            ' provider_id: {}')
    stmt = stmt.format(schema_name,
                       provider,
                       simulate,
                       provider_id)
    LOG.info(stmt)
    _remove_expired_data(schema_name, provider, simulate, provider_id)


@celery.task(name='masu.processor.tasks.update_summary_tables',
             queue_name='reporting')
def update_summary_tables(schema_name, provider, start_date, end_date=None,
                          manifest_id=None):
    """Populate the summary tables for reporting.

    Args:
        schema_name (str) The DB schema name.
        provider    (str) The provider type.
        report_dict (dict) The report data dict from previous task.
        start_date  (str) The date to start populating the table.
        end_date    (str) The date to end on.

    Returns
        None

    """
    stmt = ('update_summary_tables called with args:\n'
            ' schema_name: {},\n'
            ' provider: {},\n'
            ' start_date: {},\n'
            ' end_date: {},\n'
            ' manifest_id: {}')
    stmt = stmt.format(schema_name,
                       provider,
                       start_date,
                       end_date,
                       manifest_id)
    LOG.info(stmt)

    report_common_db = ReportingCommonDBAccessor()
    column_map = report_common_db.column_map
    report_common_db.close_session()
    report_db = ReportDBAccessor(schema=schema_name, column_map=column_map)

    report_db.update_summary_tables(provider, start_date, end_date, manifest_id)
    report_db.commit()
    report_db.close_connections()
    report_db.close_session()
