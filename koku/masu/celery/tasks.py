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

from celery.utils.log import get_task_logger
from dateutil.relativedelta import relativedelta

from koku.celery import CELERY as celery
from masu.external.date_accessor import DateAccessor
from masu.processor.orchestrator import Orchestrator
from masu.util.upload import query_and_upload_to_s3

LOG = get_task_logger(__name__)


@celery.task(name='masu.celery.tasks.check_report_updates')
def check_report_updates():
    """Scheduled task to initiate scanning process on a regular interval."""
    orchestrator = Orchestrator()
    orchestrator.prepare()


@celery.task(name='masu.celery.tasks.remove_expired_data')
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
        SELECT ds.*, a.account_id, a.account_alias, b.*
        FROM
            {schema}.reporting_awscostentrylineitem_daily_summary ds
            JOIN {schema}.reporting_awsaccountalias a ON a.id = ds.account_alias_id
            JOIN {schema}.reporting_awscostentrybill b ON b.id = ds.cost_entry_bill_id
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
        WHERE ds.usage_date_time BETWEEN %(start_date)s AND %(end_date)s
        """,
    ),
    TableExportSetting(
        'ocp',
        'reporting_ocpawscostlineitem_daily_summary',
        True,
        """
        SELECT ds.*, a.account_id, aa.account_alias, b.*
        FROM
            {schema}.reporting_ocpawscostlineitem_daily_summary ds
            JOIN {schema}.reporting_awsaccountalias aa ON aa.id = ds.account_alias_id
            JOIN {schema}.reporting_awscostentrybill b ON b.id = ds.account_alias_id
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
            JOIN {schema}.reporting_awsaccountalias aa ON aa.id = ds.account_alias_id
            JOIN {schema}.reporting_awscostentrybill b ON b.id = ds.account_alias_id
        WHERE ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
        """,
    ),
    TableExportSetting(
        'ocp',
        'reporting_ocpstoragelineitem_daily_summary',
        True,
        """
        SELECT ds.*
        FROM {schema}.reporting_ocpstoragelineitem_daily_summary ds
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


@celery.task(name='masu.celery.tasks.upload_normalized_data', queue_name='upload')
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
