#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Summary Updater for AWS Parquet files."""
import calendar
import logging

import ciso8601
from dateutil.relativedelta import relativedelta
from django.conf import settings
from tenant_schemas.utils import schema_context

from koku.pg_partition import PartitionHandlerMixin
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.common import date_range_pair
from masu.util.common import determine_if_full_summary_update_needed
from reporting.provider.aws.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class AWSReportParquetSummaryUpdater(PartitionHandlerMixin):
    """Class to update AWS report parquet summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish parquet summary processor."""
        self._schema = schema
        self._provider = provider
        self._manifest = manifest
        self._date_accessor = DateAccessor()

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""
        with AWSReportDBAccessor(self._schema) as accessor:
            # This is the normal processing route
            if self._manifest:
                # Override the bill date to correspond with the manifest
                bill_date = self._manifest.billing_period_start_datetime.date()
                bills = accessor.get_cost_entry_bills_query_by_provider(self._provider.uuid)
                bills = bills.filter(billing_period_start=bill_date).all()
                first_bill = bills.filter(billing_period_start=bill_date).first()
                do_month_update = False
                with schema_context(self._schema):
                    if first_bill:
                        do_month_update = determine_if_full_summary_update_needed(first_bill)
                if do_month_update:
                    last_day_of_month = calendar.monthrange(bill_date.year, bill_date.month)[1]
                    start_date = bill_date
                    end_date = bill_date.replace(day=last_day_of_month)
                    start_date, end_date = self._adjust_start_date_if_finalized(bill_date, start_date, end_date)
                    msg = f"Overriding start date to {start_date} and end date to {end_date}."
                    LOG.info(msg)

        if isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()

        return start_date, end_date

    def _adjust_start_date_if_finalized(self, bill_date, start_date, end_date):
        """If the bill date is from a prior month, check for an invoice ID and adjust start date."""
        now_utc = DateAccessor().today()

        is_previous_month = bill_date.year != now_utc.year or bill_date.month != now_utc.month
        if is_previous_month:
            with AWSReportDBAccessor(self._schema) as accessor:
                invoice_ids = accessor.check_for_invoice_id_trino(str(self._provider.uuid), bill_date)
                if invoice_ids:
                    msg = f"Report for billing date {bill_date} is finalized."
                    LOG.info(msg)
                else:
                    msg = f"Report for billing date {bill_date} is NOT finalized."
                    LOG.info(msg)
                    start_date = end_date - relativedelta(days=2)
        return start_date, end_date

    def update_daily_tables(self, start_date, end_date, **kwargs):
        """Populate the daily tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str): A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(start_date, end_date)
        LOG.info("update_daily_tables for: %s-%s", str(start_date), str(end_date))

        return start_date, end_date

    def update_summary_tables(self, start_date, end_date, **kwargs):
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

        with CostModelDBAccessor(self._schema, self._provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        with AWSReportDBAccessor(self._schema) as accessor:
            # Need these bills on the session to update dates after processing
            with schema_context(self._schema):
                bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
                bill_ids = [str(bill.id) for bill in bills]
                current_bill_id = bills.first().id if bills else None

            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                LOG.info(
                    "Updating AWS report summary tables from parquet: \n\tSchema: %s"
                    "\n\tProvider: %s \n\tDates: %s - %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                )
                filters = {
                    "cost_entry_bill_id": current_bill_id
                }  # Use cost_entry_bill_id to leverage DB index on DELETE
                accessor.delete_line_item_daily_summary_entries_for_date_range_raw(
                    self._provider.uuid, start, end, filters
                )
                accessor.populate_line_item_daily_summary_table_trino(
                    start, end, self._provider.uuid, current_bill_id, markup_value
                )
                accessor.populate_ui_summary_tables(start, end, self._provider.uuid)
                # accessor.populate_enabled_tag_keys(start, end, bill_ids)
            accessor.populate_tags_summary_table(bill_ids, start_date, end_date)
            accessor.populate_category_summary_table(bill_ids, start_date, end_date)

            # accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, bill_ids)
            for bill in bills:
                if bill.summary_data_creation_datetime is None:
                    bill.summary_data_creation_datetime = self._date_accessor.today_with_timezone("UTC")
                bill.summary_data_updated_datetime = self._date_accessor.today_with_timezone("UTC")
                bill.save()

        return start_date, end_date
