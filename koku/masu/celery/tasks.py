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
import calendar
import collections
from datetime import date

from botocore.exceptions import ClientError
from celery.exceptions import MaxRetriesExceededError
from celery.utils.log import get_task_logger
from dateutil.relativedelta import relativedelta
from django.conf import settings

from api.dataexport.models import DataExportRequest
from api.dataexport.syncer import AwsS3Syncer, SyncedFileInColdStorageError
from koku.celery import app
from masu.external.date_accessor import DateAccessor
from masu.processor.orchestrator import Orchestrator
from masu.util.upload import query_and_upload_to_s3

LOG = get_task_logger(__name__)


@app.task(name='masu.celery.tasks.check_report_updates', bind=True)
def check_report_updates(self):
    """Scheduled task to initiate scanning process on a regular interval."""
    orchestrator = Orchestrator()
    orchestrator.prepare(task=self)


@app.task(name='masu.celery.tasks.remove_expired_data')
def remove_expired_data():
    """Scheduled task to initiate a job to remove expired report data."""
    today = DateAccessor().today()
    LOG.info('Removing expired data at %s', str(today))
    orchestrator = Orchestrator()
    orchestrator.remove_expired_report_data()


TableExportSetting = collections.namedtuple(
    'TableExportSetting', ['provider', 'output_name', 'iterate_daily', 'sql']
)
TableExportSetting.__doc__ = """\
Settings for exporting table data using a custom SQL query.

- provider (str): the provider service's name (e.g. "aws", "azure", "ocp")
- output_name (str): a name to use when saving the query's results
- iterate_daily (bool): if True, the query should be run once per day over a date range
- sql (str): raw SQL query to execute to gather table data
"""

table_export_settings = [
    TableExportSetting(
        'aws',
        'reporting_awscostentrylineitem',
        False,
        """
        SELECT * FROM {schema}.reporting_awscostentrylineitem
        LEFT OUTER JOIN {schema}.reporting_awscostentrybill
            ON (reporting_awscostentrylineitem.cost_entry_bill_id = reporting_awscostentrybill.id)
        LEFT OUTER JOIN {schema}.reporting_awscostentry
            ON (reporting_awscostentrylineitem.cost_entry_id = reporting_awscostentry.id)
        LEFT OUTER JOIN {schema}.reporting_awscostentryproduct
            ON (reporting_awscostentrylineitem.cost_entry_product_id = reporting_awscostentryproduct.id)
        LEFT OUTER JOIN {schema}.reporting_awscostentryreservation
            ON (reporting_awscostentrylineitem.cost_entry_reservation_id = reporting_awscostentryreservation.id)
        LEFT OUTER JOIN {schema}.reporting_awscostentrypricing
            ON (reporting_awscostentrylineitem.cost_entry_pricing_id = reporting_awscostentrypricing.id)
        WHERE reporting_awscostentry.interval_start BETWEEN %(start_date)s AND %(end_date)s
        OR reporting_awscostentry.interval_end BETWEEN %(start_date)s AND %(end_date)s;
        """,
    ),
    TableExportSetting(
        'ocp',
        'reporting_ocpusagelineitem',
        False,
        """
        SELECT * FROM {schema}.reporting_ocpusagelineitem
        LEFT OUTER JOIN {schema}.reporting_ocpusagereport
            ON (reporting_ocpusagelineitem.report_id = reporting_ocpusagereport.id)
        LEFT OUTER JOIN {schema}.reporting_ocpusagereportperiod
            ON (reporting_ocpusagelineitem.report_period_id = reporting_ocpusagereportperiod.id)
        WHERE reporting_ocpusagereport.interval_start BETWEEN %(start_date)s AND %(end_date)s
        OR reporting_ocpusagereport.interval_end BETWEEN %(start_date)s AND %(end_date)s;
        """,
    ),
    TableExportSetting(
        'ocp',
        'reporting_ocpstoragelineitem',
        False,
        """
        SELECT * FROM {schema}.reporting_ocpstoragelineitem
        LEFT OUTER JOIN {schema}.reporting_ocpusagereport
            ON (reporting_ocpstoragelineitem.report_id = reporting_ocpusagereport.id)
        LEFT OUTER JOIN {schema}.reporting_ocpusagereportperiod
            ON (reporting_ocpstoragelineitem.report_period_id = reporting_ocpusagereportperiod.id)
        WHERE reporting_ocpusagereport.interval_start BETWEEN %(start_date)s AND %(end_date)s
        OR reporting_ocpusagereport.interval_end BETWEEN %(start_date)s AND %(end_date)s;
        """,
    ),
    TableExportSetting(
        'azure',
        'reporting_azurecostentrylineitem_daily',
        False,
        """
        SELECT * FROM {schema}.reporting_azurecostentrylineitem_daily
        LEFT OUTER JOIN {schema}.reporting_azurecostentrybill
            ON (reporting_azurecostentrylineitem_daily.cost_entry_bill_id = reporting_azurecostentrybill.id)
        LEFT OUTER JOIN {schema}.reporting_azurecostentryproductservice
            ON (reporting_azurecostentrylineitem_daily.cost_entry_product_id
                = reporting_azurecostentryproductservice.id)
        LEFT OUTER JOIN {schema}.reporting_azuremeter
            ON (reporting_azurecostentrylineitem_daily.meter_id = reporting_azuremeter.id)
        WHERE reporting_azurecostentrybill.billing_period_start BETWEEN %(start_date)s AND %(end_date)s
        OR reporting_azurecostentrybill.billing_period_end BETWEEN %(start_date)s AND %(end_date)s;
        """,
    ),
    TableExportSetting(
        'aws',
        'reporting_awscostentrylineitem_daily_summary',
        True,
        """
        SELECT ds.*, aa.account_id, aa.account_alias, b.*
        FROM
            {schema}.reporting_awscostentrylineitem_daily_summary ds
            JOIN {schema}.reporting_awscostentrybill b ON b.id = ds.cost_entry_bill_id
            LEFT JOIN {schema}.reporting_awsaccountalias aa ON aa.id = ds.account_alias_id
            -- LEFT JOIN because sometimes this doesn't exist, but it's unclear why.
            -- It seems that "real" data has it, but fake data from AWS-local+nise does not.
        WHERE ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
        """,
    ),
    TableExportSetting(
        'azure',
        'reporting_azurecostentrylineitem_daily_summary',
        True,
        """
        SELECT ds.*, b.*, m.*
        FROM
            {schema}.reporting_azurecostentrylineitem_daily_summary ds
            JOIN {schema}.reporting_azurecostentrybill b ON b.id = ds.cost_entry_bill_id
            JOIN {schema}.reporting_azuremeter m ON m.id = ds.meter_id
        WHERE ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
        """,
    ),
    TableExportSetting(
        'ocp',
        'reporting_ocpawscostlineitem_daily_summary',
        True,
        """
        SELECT ds.*, aa.account_id, aa.account_alias, b.*
        FROM
            {schema}.reporting_ocpawscostlineitem_daily_summary ds
            JOIN {schema}.reporting_awscostentrybill b ON b.id = ds.account_alias_id
            LEFT JOIN {schema}.reporting_awsaccountalias aa ON aa.id = ds.account_alias_id
            -- LEFT JOIN because sometimes this doesn't exist, but it's unclear why.
            -- It seems that "real" data has it, but fake data from AWS-local+nise does not.
        WHERE ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
        """,
    ),
    TableExportSetting(
        'ocp',
        'reporting_ocpawscostlineitem_project_daily_summary',
        True,
        """
        SELECT ds.*, aa.account_id, aa.account_alias, b.*
        FROM
            {schema}.reporting_ocpawscostlineitem_project_daily_summary ds
            JOIN {schema}.reporting_awscostentrybill b ON b.id = ds.account_alias_id
            LEFT JOIN {schema}.reporting_awsaccountalias aa ON aa.id = ds.account_alias_id
            -- LEFT JOIN because sometimes this doesn't exist, but it's unclear why.
            -- It seems that "real" data has it, but fake data from AWS-local+nise does not.
        WHERE ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
        """,
    ),
    TableExportSetting(
        'ocp',
        'reporting_ocpusagelineitem_daily_summary',
        True,
        """
        SELECT ds.*
        FROM {schema}.reporting_ocpusagelineitem_daily_summary ds
        WHERE ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
        """,
    ),
]


@app.task(name='masu.celery.tasks.upload_normalized_data', queue_name='upload')
def upload_normalized_data():
    """Scheduled task to export normalized data to s3."""
    curr_date = DateAccessor().today()
    curr_month_range = calendar.monthrange(curr_date.year, curr_date.month)
    curr_month_first_day = date(year=curr_date.year, month=curr_date.month, day=1)
    curr_month_last_day = date(year=curr_date.year, month=curr_date.month, day=curr_month_range[1])

    previous_month = curr_date - relativedelta(months=1)

    prev_month_range = calendar.monthrange(previous_month.year, previous_month.month)
    prev_month_first_day = date(year=previous_month.year, month=previous_month.month, day=1)
    prev_month_last_day = date(year=previous_month.year, month=previous_month.month, day=prev_month_range[1])

    accounts, _ = Orchestrator.get_accounts()

    # Deduplicate schema_name since accounts may have the same schema_name but different providers
    schemas = set(account['schema_name'] for account in accounts)
    for schema in schemas:
        for table in table_export_settings:
            # Upload this month's reports
            query_and_upload_to_s3(schema, table, (curr_month_first_day, curr_month_last_day))

            # Upload last month's reports
            query_and_upload_to_s3(schema, table, (prev_month_first_day, prev_month_last_day))


@app.task(name='masu.celery.tasks.sync_data_to_customer',
          queue_name='customer_data_sync',
          retry_kwargs={'max_retries': 5,
                        'countdown': settings.COLD_STORAGE_RETRIVAL_WAIT_TIME})
def sync_data_to_customer(dump_request_uuid):
    """
    Scheduled task to sync normalized data to our customers S3 bucket.

    If the sync request raises SyncedFileInColdStorageError, this task
    will automatically retry in a set amount of time. This time is to give
    the storage solution time to retrieve a file from cold storage.
    This task will retry 5 times, and then fail.

    """
    dump_request = DataExportRequest.objects.get(uuid=dump_request_uuid)
    dump_request.status = DataExportRequest.PROCESSING
    dump_request.save()

    try:
        syncer = AwsS3Syncer(settings.S3_BUCKET_NAME)
        syncer.sync_bucket(
            dump_request.created_by.customer.schema_name,
            dump_request.bucket_name,
            (dump_request.start_date, dump_request.end_date))
    except ClientError:
        LOG.exception(
            f'Encountered an error while processing DataExportRequest '
            f'{dump_request.uuid}, for {dump_request.created_by}.')
        dump_request.status = DataExportRequest.ERROR
        dump_request.save()
        return
    except SyncedFileInColdStorageError:
        LOG.info(
            f'One of the requested files is currently in cold storage for '
            f'DataExportRequest {dump_request.uuid}. This task will automatically retry.')
        dump_request.status = DataExportRequest.WAITING
        dump_request.save()
        try:
            raise sync_data_to_customer.retry(countdown=10, max_retries=5)
        except MaxRetriesExceededError:
            LOG.exception(
                f'Max retires exceeded for restoring a file in cold storage for '
                f'DataExportRequest {dump_request.uuid}, for {dump_request.created_by}.')
            dump_request.status = DataExportRequest.ERROR
            dump_request.save()
            return
    dump_request.status = DataExportRequest.COMPLETE
    dump_request.save()
