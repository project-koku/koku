#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates report summary tables in the database."""
import calendar
import logging

from tenant_schemas.utils import schema_context

from koku.pg_partition import PartitionHandlerMixin
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.common import date_range_pair
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.provider.ocp.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class OCPReportSummaryUpdater(PartitionHandlerMixin):
    """Class to update OCP report summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema
        self._provider = provider
        self._manifest = manifest
        self._cluster_id = get_cluster_id_from_provider(self._provider.uuid)
        self._date_accessor = DateAccessor()

    def update_daily_tables(self, start_date, end_date):
        """Populate the daily tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(start_date, end_date)
        for start, end in date_range_pair(start_date, end_date):
            LOG.info(
                "Updating OpenShift report daily tables for \n\tSchema: %s "
                "\n\tProvider: %s \n\tCluster: %s \n\tDates: %s - %s",
                self._schema,
                self._provider.uuid,
                self._cluster_id,
                start,
                end,
            )
            with OCPReportDBAccessor(self._schema) as accessor:
                accessor.populate_node_label_line_item_daily_table(start, end, self._cluster_id)
                accessor.populate_line_item_daily_table(start, end, self._cluster_id)
                accessor.populate_storage_line_item_daily_table(start, end, self._cluster_id)

        return start_date, end_date

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(start_date, end_date)
        with schema_context(self._schema):
            self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

        report_period = None
        with OCPReportDBAccessor(self._schema) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(self._provider.uuid, start_date)
            with schema_context(self._schema):
                report_period_ids = [report_period.id]
            for start, end in date_range_pair(start_date, end_date):
                LOG.info(
                    "Updating OpenShift report summary tables for \n\tSchema: %s "
                    "\n\tProvider: %s \n\tCluster: %s \n\tDates: %s - %s",
                    self._schema,
                    self._provider.uuid,
                    self._cluster_id,
                    start,
                    end,
                )
                accessor.populate_line_item_daily_summary_table(start, end, self._cluster_id, self._provider.uuid)
                accessor.populate_storage_line_item_daily_summary_table(
                    start, end, self._cluster_id, self._provider.uuid
                )
                accessor.populate_ui_summary_tables(start, end, self._provider.uuid)
            accessor.populate_pod_label_summary_table(report_period_ids, start_date, end_date)
            accessor.populate_volume_label_summary_table(report_period_ids, start_date, end_date)
            accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, report_period_ids)

            if report_period.summary_data_creation_datetime is None:
                report_period.summary_data_creation_datetime = self._date_accessor.today_with_timezone("UTC")
            report_period.summary_data_updated_datetime = self._date_accessor.today_with_timezone("UTC")
            report_period.save()

        return start_date, end_date

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""
        # Default to this month's bill
        with OCPReportDBAccessor(self._schema) as accessor:
            if self._manifest:
                # Override the bill date to correspond with the manifest
                bill_date = self._manifest.billing_period_start_datetime.date()
                report_periods = accessor.get_usage_period_query_by_provider(self._provider.uuid)
                report_periods = report_periods.filter(report_period_start=bill_date).all()
                do_month_update = True
                with schema_context(self._schema):
                    if report_periods is not None and len(report_periods) > 0:
                        do_month_update = self._determine_if_full_summary_update_needed(report_periods[0])
                if do_month_update:
                    last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]
                    start_date = bill_date.strftime("%Y-%m-%d")
                    end_date = bill_date.replace(day=last_day_of_month)
                    end_date = end_date.strftime("%Y-%m-%d")
                    LOG.info("Overriding start and end date to process full month.")
                LOG.info("Returning start: %s, end: %s", str(start_date), str(end_date))
        return start_date, end_date

    def _determine_if_full_summary_update_needed(self, report_period):
        """Decide whether to update summary tables for full billing period."""
        summary_creation = report_period.summary_data_creation_datetime
        is_done_processing = False
        with ReportManifestDBAccessor() as manifest_accesor:
            is_done_processing = manifest_accesor.manifest_ready_for_summary(self._manifest.id)
        is_new_period = summary_creation is None

        # Run the full month if this is the first time we've seen this report
        # period
        if is_done_processing and is_new_period:
            return True

        return False
