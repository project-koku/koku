import calendar
import logging

import ciso8601
from django.conf import settings
from tenant_schemas.utils import schema_context

from koku.pg_partition import PartitionHandlerMixin
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.common import date_range_pair
from masu.util.common import determine_if_full_summary_update_needed
from reporting.provider.azure.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class AzureReportParquetSummaryUpdater(PartitionHandlerMixin):
    """Class to update Azure report parquet summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish parquet summary processor."""
        self._schema = schema
        self._provider = provider
        self._manifest = manifest
        self._date_accessor = DateAccessor()

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""
        with AzureReportDBAccessor(self._schema) as accessor:
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
                    LOG.info("Overriding start and end date to process full month.")

        if isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()

        return start_date, end_date

    def update_daily_tables(self, start_date, end_date):
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

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str) A start date and end date.

        """
        start_date, end_date = self._get_sql_inputs(start_date, end_date)

        with CostModelDBAccessor(self._schema, self._provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        with schema_context(self._schema):
            self._handle_partitions(self._schema, UI_SUMMARY_TABLES, start_date, end_date)

        with AzureReportDBAccessor(self._schema) as accessor:
            # Need these bills on the session to update dates after processing
            with schema_context(self._schema):
                bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
                bill_ids = [str(bill.id) for bill in bills]
                current_bill_id = bills.first().id if bills else None

            for start, end in date_range_pair(start_date, end_date, step=settings.TRINO_DATE_STEP):
                LOG.info(
                    "Updating Azure report summary tables via Presto: \n\tSchema: %s"
                    "\n\tProvider: %s \n\tDates: %s - %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                )
                accessor.delete_line_item_daily_summary_entries_for_date_range(self._provider.uuid, start, end)
                accessor.populate_line_item_daily_summary_table_presto(
                    start, end, self._provider.uuid, current_bill_id, markup_value
                )
                accessor.populate_enabled_tag_keys(start, end, bill_ids)
                accessor.populate_ui_summary_tables(start, end, self._provider.uuid)
            accessor.populate_tags_summary_table(bill_ids, start_date, end_date)
            accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, bill_ids)
            for bill in bills:
                if bill.summary_data_creation_datetime is None:
                    bill.summary_data_creation_datetime = self._date_accessor.today_with_timezone("UTC")
                bill.summary_data_updated_datetime = self._date_accessor.today_with_timezone("UTC")
                bill.save()

        return start_date, end_date
