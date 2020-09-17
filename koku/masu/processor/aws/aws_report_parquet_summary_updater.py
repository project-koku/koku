import logging

from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.util.common import date_range_pair

LOG = logging.getLogger(__name__)


class AWSReportParquetSummaryUpdater:
    """Class to update AWS report parquet summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish parquet summary processor."""
        self._schema = schema
        self._provider = provider
        self._manifest = manifest

    def _get_sql_inputs(self, start_date, end_date):
        """Get the required inputs for running summary SQL."""

        return start_date, end_date

    def update_daily_tables(self, start_date, end_date):
        """Populate the daily tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            (str, str): A start date and end date.

        """
        LOG.info("update_daily_tables for: %s-%s", str(start_date), str(end_date))
        start_date, end_date = self._get_sql_inputs(start_date, end_date)

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
            for start, end in date_range_pair(start_date, end_date):
                LOG.info(
                    "Updating AWS report summary tables from parquet: \n\tSchema: %s"
                    "\n\tProvider: %s \n\tDates: %s - %s",
                    self._schema,
                    self._provider.uuid,
                    start,
                    end,
                )
                accessor.populate_line_item_daily_summary_table_from_parquet(
                    start, end, self._provider.uuid, self._manifest.id, markup_value
                )

        return start_date, end_date
