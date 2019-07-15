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
import logging

from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.ocp.common import get_cluster_id_from_provider

LOG = logging.getLogger(__name__)


class OCPReportSummaryUpdater:
    """Class to update OCP report summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        self._schema_name = schema
        self._provider = provider
        self._manifest = manifest
        self._cluster_id = get_cluster_id_from_provider(self._provider.uuid)
        with ReportingCommonDBAccessor() as reporting_common:
            self._column_map = reporting_common.column_map
        self._date_accessor = DateAccessor()

    def update_daily_tables(self, start_date, end_date):
        """Populate the daily tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(
            start_date,
            end_date
        )
        LOG.info('Updating OpenShift report daily tables for \n\tSchema: %s '
                 '\n\tProvider: %s \n\tCluster: %s \n\tDates: %s - %s',
                 self._schema_name, self._provider.uuid, self._cluster_id,
                 start_date, end_date)
        with OCPReportDBAccessor(self._schema_name, self._column_map) as accessor:
            accessor.populate_line_item_daily_table(start_date, end_date, self._cluster_id)
            accessor.populate_storage_line_item_daily_table(start_date, end_date, self._cluster_id)

        return start_date, end_date

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(
            start_date,
            end_date
        )
        LOG.info('Updating OpenShift report summary tables for \n\tSchema: %s '
                 '\n\tProvider: %s \n\tCluster: %s \n\tDates: %s - %s',
                 self._schema_name, self._provider.uuid, self._cluster_id,
                 start_date, end_date)
        with OCPReportDBAccessor(self._schema_name, self._column_map) as accessor:
            report_periods = accessor.report_periods_for_provider_id(self._provider.id, start_date)
            accessor.populate_line_item_daily_summary_table(start_date, end_date, self._cluster_id)
            accessor.populate_pod_label_summary_table()
            accessor.populate_storage_line_item_daily_summary_table(start_date, end_date, self._cluster_id)
            accessor.populate_volume_claim_label_summary_table()
            accessor.populate_volume_label_summary_table()

            for period in report_periods:
                if period.summary_data_creation_datetime is None:
                    period.summary_data_creation_datetime = \
                        self._date_accessor.today_with_timezone('UTC')
                period.summary_data_updated_datetime = \
                    self._date_accessor.today_with_timezone('UTC')

            accessor.commit()

        return start_date, end_date

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""
        # Default to this month's bill
        with OCPReportDBAccessor(self._schema_name, self._column_map) as accessor:
            if self._manifest:
                # Override the bill date to correspond with the manifest
                bill_date = self._manifest.billing_period_start_datetime.date()
                report_periods = accessor.get_usage_period_query_by_provider(
                    self._provider.id
                )
                report_periods = report_periods.filter_by(
                    report_period_start=bill_date
                ).all()

                do_month_update = True
                if report_periods is not None and len(report_periods) > 0:
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

            return start_date, end_date

    def _determine_if_full_summary_update_needed(self, report_period):
        """Decide whether to update summary tables for full billing period."""
        processed_files = self._manifest.num_processed_files
        total_files = self._manifest.num_total_files

        summary_creation = report_period.summary_data_creation_datetime
        is_done_processing = processed_files == total_files
        is_new_period = summary_creation is None

        # Run the full month if this is the first time we've seen this report
        # period
        if is_done_processing and is_new_period:
            return True

        return False
