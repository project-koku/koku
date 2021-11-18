#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates report summary tables in the database."""
import calendar
import logging
from datetime import datetime

import ciso8601
from django.conf import settings
from tenant_schemas.utils import schema_context

from koku.pg_partition import PartitionHandlerMixin
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.common import date_range_pair
from masu.util.common import determine_if_full_summary_update_needed
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.provider.ocp.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class OCPReportParquetSummaryUpdater(PartitionHandlerMixin):
    """Class to update OCP report summary data from Presto/Parquet data."""

    def __init__(self, schema, provider, manifest):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema
        self._provider = provider
        self._manifest = manifest
        self._cluster_id = get_cluster_id_from_provider(self._provider.uuid)
        self._cluster_alias = get_cluster_alias_from_cluster_id(self._cluster_id)
        self._date_accessor = DateAccessor()

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""
        with OCPReportDBAccessor(self._schema) as accessor:
            # This is the normal processing route
            if self._manifest:
                # Override the bill date to correspond with the manifest
                bill_date = self._manifest.billing_period_start_datetime.date()
                report_periods = accessor.get_usage_period_query_by_provider(self._provider.uuid)
                report_periods = report_periods.filter(report_period_start=bill_date).all()
                first_period = report_periods.first()
                do_month_update = False
                with schema_context(self._schema):
                    if first_period:
                        do_month_update = determine_if_full_summary_update_needed(first_period)
                if do_month_update:
                    last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]
                    start_date = bill_date
                    end_date = bill_date.replace(day=last_day_of_month)
                    LOG.info("Overriding start and end date to process full month.")

        if isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()

        return start_date, end_date

    def _check_parquet_date_range(self, start_date, end_date):
        """Make sure we don't summarize for a date range we don't have data for."""
        start_datetime = datetime(start_date.year, start_date.month, start_date.day)
        with OCPReportDBAccessor(self._schema) as accessor:
            min_timestamp, __ = accessor.get_max_min_timestamp_from_parquet(self._provider.uuid, start_date, end_date)
            if min_timestamp > start_datetime:
                start_date = min_timestamp.date()
        return start_date, end_date

    def update_daily_tables(self, start_date, end_date):
        """Populate the daily tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(start_date, end_date)
        LOG.info("NO-OP update_daily_tables for: %s-%s", str(start_date), str(end_date))

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
        start_date, end_date = self._check_parquet_date_range(start_date, end_date)

        with schema_context(self._schema):
            self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

        with OCPReportDBAccessor(self._schema) as accessor:
            with schema_context(self._schema):
                report_period = accessor.report_periods_for_provider_uuid(self._provider.uuid, start_date)
                report_period_id = report_period.id

            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                LOG.info(
                    "Updating OpenShift report summary tables for \n\tSchema: %s "
                    "\n\tProvider: %s \n\tCluster: %s \n\tReport Period ID: %s \n\tDates: %s - %s",
                    self._schema,
                    self._provider.uuid,
                    self._cluster_id,
                    report_period_id,
                    start,
                    end,
                )
                # This will process POD and STORAGE together
                accessor.delete_line_item_daily_summary_entries_for_date_range(self._provider.uuid, start, end)
                accessor.populate_line_item_daily_summary_table_presto(
                    start, end, report_period_id, self._cluster_id, self._cluster_alias, self._provider.uuid
                )
                accessor.populate_ui_summary_tables(start, end, self._provider.uuid)

            # This will process POD and STORAGE together
            LOG.info(
                "Updating OpenShift label summary tables for \n\tSchema: %s " "\n\tReport Period IDs: %s",
                self._schema,
                [report_period_id],
            )
            accessor.populate_pod_label_summary_table([report_period_id], start_date, end_date)
            accessor.populate_volume_label_summary_table([report_period_id], start_date, end_date)
            accessor.populate_openshift_cluster_information_tables(
                self._provider, self._cluster_id, self._cluster_alias, start_date, end_date
            )
            accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, [report_period_id])

            LOG.info("Updating OpenShift report periods")
            if report_period.summary_data_creation_datetime is None:
                report_period.summary_data_creation_datetime = self._date_accessor.today_with_timezone("UTC")
            report_period.summary_data_updated_datetime = self._date_accessor.today_with_timezone("UTC")
            report_period.save()

        return start_date, end_date
