import logging

import ciso8601
from tenant_schemas.utils import schema_context

from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


class AWSReportParquetSummaryUpdater:
    """Class to update AWS report parquet summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish parquet summary processor."""
        self._schema = schema
        self._provider = provider
        self._manifest = manifest
        self._date_accessor = DateAccessor()

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""
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

        with AWSReportDBAccessor(self._schema) as accessor:
            # Need these bills on the session to update dates after processing
            with schema_context(self._schema):
                bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
                bill_ids = [str(bill.id) for bill in bills]
                current_bill_id = bills.first().id if bills else None

            # for start, end in date_range_pair(start_date, end_date):
            LOG.info(
                "Updating AWS report summary tables from parquet: \n\tSchema: %s"
                "\n\tProvider: %s \n\tDates: %s - %s",
                self._schema,
                self._provider.uuid,
                start_date,
                end_date,
            )
            accessor.populate_line_item_daily_summary_table_presto(
                start_date, end_date, self._provider.uuid, current_bill_id, markup_value
            )
            accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            accessor.populate_tags_summary_table(bill_ids)
            accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, bill_ids)
            for bill in bills:
                if bill.summary_data_creation_datetime is None:
                    bill.summary_data_creation_datetime = self._date_accessor.today_with_timezone("UTC")
                bill.summary_data_updated_datetime = self._date_accessor.today_with_timezone("UTC")
                bill.save()

        return start_date, end_date
