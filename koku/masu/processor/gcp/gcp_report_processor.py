"""Processor for GCP Cost Usage Reports."""
import logging
from collections import OrderedDict
from datetime import datetime
from numbers import Number
from os import remove

import pandas
import pytz
from dateutil import parser
from django.conf import settings

from masu.config import Config
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.processor.report_processor_base import ReportProcessorBase
from masu.util import common as utils
from reporting.provider.gcp.models import GCPCostEntryBill, GCPCostEntryLineItemDaily, GCPProject


LOG = logging.getLogger(__name__)


class ProcessedGCPReport:
    """Kept in memory object of report items."""

    def __init__(self):
        """Initialize new cost entry containers."""
        self.line_items = []
        self.unique_line_items = {}
        self.bills = {}
        self.projects = {}

    def remove_processed_rows(self):
        """Clear a batch of rows after they've been saved."""
        self.line_items = []
        self.unique_line_items = {}


class GCPReportProcessor(ReportProcessorBase):
    """Cost Usage Report processor."""

    def __init__(self, schema_name, report_path, compression,
                 provider_uuid, manifest_id=None):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        super().__init__(
            schema_name=schema_name,
            report_path=report_path,
            compression=compression,
            provider_uuid=provider_uuid,
            manifest_id=manifest_id,
            processed_report=ProcessedGCPReport()
        )

        self.line_item_table = GCPCostEntryLineItemDaily()
        self.line_item_table_name = self.line_item_table._meta.db_table
        self._report_name = report_path
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        self._schema = schema_name

        # Gather database accessors
        with ReportingCommonDBAccessor() as report_common_db:
            self.column_map = report_common_db.column_map

        LOG.info('Initialized report processor for file: %s and schema: %s',
                 report_path, self._schema)

        self.line_item_columns = None

    def _get_or_create_cost_entry_bill(self, row, report_db_accessor):
        """Get or Create a GCP cost entry bill object.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row.

        Returns:
             (string) An id of a GCP Bill.

        """
        table_name = GCPCostEntryBill
        start_time = row['Start Time']

        report_date_range = utils.month_date_range(parser.parse(start_time))
        start_date, end_date = report_date_range.split('-')

        start_date_utc = parser.parse(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = parser.parse(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        data = {
            'billing_period_start': datetime.strftime(start_date_utc, '%Y-%m-%d %H:%M%z'),
            'billing_period_end': datetime.strftime(end_date_utc, '%Y-%m-%d %H:%M%z'),
            'provider_id': self._provider_uuid,
        }

        key = (start_date_utc, self._provider_uuid)
        if key in self.processed_report.bills:
            return self.processed_report.bills[key]

        bill_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data,
            conflict_columns=['billing_period_start', 'provider_id']
        )
        report_db_accessor.commit()
        self.processed_report.bills[key] = bill_id

        return bill_id

    def _get_or_create_gcp_project(self, row, report_db_accessor):
        """Get or Create a GCPProject.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row.

        Returns:
             (string) A GCP Project instance id with project_id matching row_id.

        """
        table_name = GCPProject
        data = self._get_data_for_table(row, table_name._meta.db_table)
        data = report_db_accessor.clean_data(
            data,
            table_name._meta.db_table
        )

        key = data['project_id']
        if key in self.processed_report.projects:
            return self.processed_report.projects[key]

        project_id = report_db_accessor.insert_on_conflict_do_nothing(
            table_name,
            data,
            conflict_columns=['project_id']
        )
        report_db_accessor.commit()

        self.processed_report.projects[key] = project_id
        return project_id

    def _create_cost_entry_line_item(self, row, bill_id, project_id, report_db_accessor):
        """Create a cost entry line item object.

        Args:
            row (OrderedDict): A dictionary representation of a CSV file row
            bill_id (string): A monthly GCPCostEntryBill
            project_id (string): A GCP Project

        """
        data = self._get_data_for_table(row, self.line_item_table_name)
        data = report_db_accessor.clean_data(
            data,
            self.line_item_table_name
        )

        data['cost_entry_bill_id'] = bill_id
        data['project_id'] = project_id

        key = (project_id, data['start_time'], data['line_item_type'])

        # If we've already seen the key in this report, we have a duplicate line item
        # and should consolidate the two lines into one.
        if key in self.processed_report.unique_line_items:
            data = self._consolidate_line_items(
                self.processed_report.unique_line_items[key],
                data)

        self.processed_report.unique_line_items[key] = data
        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    def _consolidate_line_items(self, line1, line2):
        """Given 2 line items consolidate them into one, by adding all numerical values together."""
        ignored_keys = ['cost_entry_bill_id', 'project_id']
        consolidated_line_item = {}
        for key, value in line1.items():
            consolidated_line_item[key] = value

            # If key is an id, ignore it during consolidation
            if key in ignored_keys:
                continue
            if isinstance(value, Number):
                consolidated_line_item[key] += line2[key]
        return consolidated_line_item

    @property
    def line_item_conflict_columns(self):
        """Create a property to check conflict on line items."""
        return ['project_id', 'line_item_type', 'start_time']

    def process(self):
        """Process GCP billing file."""
        row_count = 0

        # Read the csv in batched chunks.
        report_csv = pandas.read_csv(self._report_path, chunksize=self._batch_size,
                                     compression='infer')

        with GCPReportDBAccessor(self._schema, self.column_map) as report_db:

            for chunk in report_csv:

                # Group the information in the csv by the start time and the project id
                report_groups = chunk.groupby(by=['Start Time', 'Project ID'])
                for group, rows in report_groups:

                    # Each row in the group contains information that we'll need to create the bill
                    # and the project. Just get the first row to pull this information.
                    first_row = OrderedDict(zip(rows.columns.tolist(), rows.iloc[0].tolist()))

                    bill_id = self._get_or_create_cost_entry_bill(first_row, report_db)

                    project_id = self._get_or_create_gcp_project(first_row, report_db)

                    for row in rows.values:
                        processed_row = OrderedDict(zip(rows.columns.tolist(), row.tolist()))
                        self._create_cost_entry_line_item(processed_row, bill_id, project_id, report_db)

                LOG.info('Saving report rows %d to %d for %s', row_count,
                         row_count + len(self.processed_report.unique_line_items),
                         self._report_name)

                # Create a temp table with all the line items, and merge the temp table to the line item table.
                # This is faster than django's bulk_create.
                temp_table = report_db.create_temp_table(
                    self.line_item_table_name,
                    drop_column='id'
                )

                # Have to put values into line_items because the parent class needs it to _save_to_db
                self.processed_report.line_items = list(self.processed_report.unique_line_items.values())
                self._save_to_db(temp_table, report_db)
                report_db.merge_temp_table(
                    self.line_item_table_name,
                    temp_table,
                    self.line_item_columns,
                    self.line_item_conflict_columns
                )

                row_count += len(self.processed_report.line_items)
                self.processed_report.remove_processed_rows()

            LOG.info('Completed report processing for file: %s and schema: %s',
                     self._report_name, self._schema)

            if not settings.DEVELOPMENT:
                LOG.info('Removing processed file: %s', self._report_path)
                remove(self._report_path)
