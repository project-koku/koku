#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Updates report summary tables in the database."""
# pylint: skip-file

import calendar
import datetime
import logging

from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


class OCPReportSummaryUpdater:
    """Class to update OCP report summary data."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        self._schema_name = schema
        self._accessor = OCPReportDBAccessor(
            schema,
            ReportingCommonDBAccessor().column_map
        )
        self._date_accessor = DateAccessor()
        self.manifest = None

    def update_summary_tables(self, start_date, end_date, manifest_id=None):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.
            manifest_id (str) A manifest to check before summarizing

        Returns
            None

        """
        LOG.info('Starting report data summarization.')
        # Validate dates as strings
        if isinstance(start_date, datetime.date):
            start_date = start_date.strftime('%Y-%m-%d')
        if isinstance(end_date, datetime.date):
            end_date = end_date.strftime('%Y-%m-%d')
        elif end_date is None:
            # Run for 1 day
            start = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            end_date = start + datetime.timedelta(days=1)
            end_date = end_date.date().strftime('%Y-%m-%d')
        LOG.info('Using start date: %s', start_date)
        LOG.info('Using end date: %s', end_date)

        # Default to this month's bill
        report_date = datetime.datetime.strptime(start_date, '%Y-%m-%d')\
            .replace(day=1).date()
        report_periods = self._accessor.get_usage_periods_by_date(report_date)

        if manifest_id is not None:
            manifest_accessor = ReportManifestDBAccessor()
            self.manifest = manifest_accessor.get_manifest_by_id(manifest_id)
            manifest_accessor.close_session()
            # Override the bill date to correspond with the manifest
            bill_date = self.manifest.billing_period_start_datetime.date()
            provider_id = self.manifest.provider_id
            report_periods = self._accessor.get_usage_period_query_by_provider(
                provider_id
            )
            report_periods = report_periods.filter_by(
                report_period_start=bill_date
            ).all()

            do_month_update = self._determine_if_full_summary_update_needed(
                report_periods[0]
            )
            if do_month_update:
                last_day_of_month = calendar.monthrange(
                    bill_date.year,
                    bill_date.month
                )[1]
                start_date = bill_date.strftime('%Y-%m-%d')
                end_date = bill_date.replace(day=last_day_of_month)
                end_date = end_date.strftime('%Y-%m-%d')
                LOG.info('Overriding start and end date to process full month.')

        LOG.info('Updating report summary tables for %s from %s to %s',
                 self._schema_name, start_date, end_date)

        self._accessor.populate_line_item_daily_table(start_date, end_date)
        self._accessor.populate_line_item_daily_summary_table(start_date,
                                                              end_date)
        self._accessor.populate_line_item_aggregate_table()

        for period in report_periods:
            if period.summary_data_creation_datetime is None:
                period.summary_data_creation_datetime = \
                    self._date_accessor.today_with_timezone('UTC')
            period.summary_data_updated_datetime = \
                self._date_accessor.today_with_timezone('UTC')

        self._accessor.commit()

    def _determine_if_full_summary_update_needed(self, report_period):
        """Decide whether to update summary tables for full billing period."""
        processed_files = self.manifest.num_processed_files
        total_files = self.manifest.num_total_files

        summary_creation = report_period.summary_data_creation_datetime
        is_done_processing = processed_files == total_files
        is_new_period = summary_creation is None

        # Run the full month if this is the first time we've seen this report
        # period
        if is_done_processing and is_new_period:
            return True

        return False

    def close_session(self):
        """Close database connections and sessions."""
        self._accessor.close_connections()
        self._accessor.close_session()
