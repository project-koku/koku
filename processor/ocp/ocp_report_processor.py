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

"""Processor for OCP Usage Reports."""

# pylint: skip-file
# Disabling for now since there are overlaps with AWSReportProcessor.
# Addressing all lint errors would impact both report processors.

import csv
import gzip
import io
import logging
from datetime import datetime
from os import path

import pytz

from masu.config import Config
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external import GZIP_COMPRESSED
from masu.processor.report_processor_base import ReportProcessorBase

LOG = logging.getLogger(__name__)


class ProcessedOCPReport:
    """Usage report transcribed to our database models.

    Effectively a struct for associated database tables.
    """

    def __init__(self):
        """Initialize new cost entry containers."""
        self.report_periods = {}
        self.reports = {}
        self.line_items = []

    def remove_processed_rows(self):
        """Clear a batch of rows from their containers."""
        self.report_periods = {}
        self.reports = {}
        self.line_items = []


class OCPReportProcessor(ReportProcessorBase):
    """OCP Usage Report processor."""

    def __init__(self, schema_name, report_path, compression):
        """Initialize the report processor.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        super().__init__(schema_name=schema_name, report_path=report_path, compression=compression)

        self._report_name = path.basename(report_path)
        self._cluster_id = report_path.split('/')[-2]

        self._datetime_format = Config.OCP_DATETIME_STR_FORMAT
        self._batch_size = Config.REPORT_PROCESSING_BATCH_SIZE

        self.processed_report = ProcessedOCPReport()

        self.report_common_db = ReportingCommonDBAccessor()
        self.column_map = self.report_common_db.column_map
        self.report_common_db.close_session()

        self.report_db = OCPReportDBAccessor(schema=self._schema_name,
                                             column_map=self.column_map)

        self.temp_table = self.report_db.create_temp_table(
            OCP_REPORT_TABLE_MAP['line_item']
        )

        self.line_item_columns = None

        self.current_usage_report_period = self.report_db.get_current_usage_period()
        self.existing_report_periods_map = self.report_db.get_report_periods()
        self.existing_report_map = self.report_db.get_reports()

        LOG.info('Initialized report processor for file: %s and schema: %s',
                 self._report_path, self._schema_name)

    def _get_file_opener(self, compression):
        """Get the file opener for the file's compression.

        Args:
            compression (str): The compression format for the file.

        Returns:
            (file opener, str): The proper file stream handler for the
                compression and the read mode for the file

        """
        if compression == GZIP_COMPRESSED:
            return gzip.open, 'rt'
        return open, 'r'    # assume uncompressed by default

    def _get_data_for_table(self, row, table_name):
        """Extract the data from a row for a specific table.

        Args:
            row (dict): A dictionary representation of a CSV file row
            table_name (str): The DB table fields are required for

        Returns:
            (dict): The data from the row keyed on the DB table's column names

        """
        column_map = self.column_map[table_name]

        return {column_map[key]: value
                for key, value in row.items()
                if key in column_map}

    def _create_report(self, row, report_period_id):
        """Create a report object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): report period object id

        Returns:
            (str): The DB id of the report object

        """
        table_name = OCP_REPORT_TABLE_MAP['report']
        start = datetime.strptime(row.get('interval_start'), Config.OCP_DATETIME_STR_FORMAT)
        end = datetime.strptime(row.get('interval_end'), Config.OCP_DATETIME_STR_FORMAT)

        if start in self.processed_report.reports:
            return self.processed_report.reports[start]

        if row.get('interval_start') in self.existing_report_map:
            return self.existing_report_map[row.get('interval_start')]

        data = {
            'report_period_id': report_period_id,
            'interval_start': start,
            'interval_end': end
        }
        report_id = self.report_db.insert_on_conflict_do_nothing(
            table_name,
            data
        )

        self.processed_report.reports[start] = report_id

        return report_id

    def _create_report_period(self, row, cluster_id):
        """Create a report period object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            cluster_id (str): cluster ID

        Returns:
            (str): The DB id of the report period object

        """
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        start = datetime.strptime(row.get('report_period_start'), Config.OCP_DATETIME_STR_FORMAT)
        end = datetime.strptime(row.get('report_period_end'), Config.OCP_DATETIME_STR_FORMAT)

        current_start = None
        if self.current_usage_report_period is not None:
            current_start = self.current_usage_report_period.report_period_start

        if current_start is not None and start.replace(tzinfo=pytz.UTC) == current_start:
            self.processed_report.report_periods[start] = self.current_usage_report_period.id
            return self.current_usage_report_period.id

        if start in self.processed_report.report_periods:
            return self.processed_report.report_periods[start]

        if row.get('report_period_start') in self.existing_report_periods_map:
            return self.existing_report_periods_map[row.get('report_period_start')]

        data = {
            'cluster_id': cluster_id,
            'report_period_start': start,
            'report_period_end': end
        }
        report_period_id = self.report_db.insert_on_conflict_do_nothing(
            table_name,
            data
        )

        self.processed_report.report_periods[start] = report_period_id

        return report_period_id

    def _create_usage_report_line_item(self,
                                       row,
                                       report_period_id,
                                       report_id):
        """Create a cost entry line item object.

        Args:
            row (dict): A dictionary representation of a CSV file row
            report_period_id (str): A report period object id
            report_id (str): A report object id

        Returns:
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        data = self._get_data_for_table(row, table_name)

        data = self.report_db.clean_data(
            data,
            table_name
        )

        data['report_period_id'] = report_period_id
        data['report_id'] = report_id

        self.processed_report.line_items.append(data)

        if self.line_item_columns is None:
            self.line_item_columns = list(data.keys())

    def _write_processed_rows_to_csv(self):
        """Output CSV content to file stream object."""
        values = [tuple(item.values())
                  for item in self.processed_report.line_items]

        file_obj = io.StringIO()
        writer = csv.writer(
            file_obj,
            delimiter='\t',
            quoting=csv.QUOTE_NONE,
            quotechar=''
        )
        writer.writerows(values)
        file_obj.seek(0)

        return file_obj

    def _save_to_db(self):
        """Save current batch of records to the database."""
        columns = tuple(self.processed_report.line_items[0].keys())
        csv_file = self._write_processed_rows_to_csv()

        # This will commit all pricing, products, and reservations
        # on the session
        self.report_db.commit()

        self.report_db.bulk_insert_rows(
            csv_file,
            self.temp_table,
            columns)

    def _update_mappings(self):
        """Update cache of database objects for reference."""
        self.existing_report_periods_map.update(self.processed_report.report_periods)
        self.existing_report_map.update(self.processed_report.reports)

        self.processed_report.remove_processed_rows()

    def remove_temp_cur_files(self, report_path):
        """Remove temporary cost usage report files."""
        LOG.info('Cleaning up temporary report files for %s', self._report_name)
        return []

    @property
    def line_item_conflict_columns(self):
        """Create a property to check conflict on line items."""
        return ['report_id', 'namespace', 'pod', 'node']

    @property
    def line_item_condition_column(self):
        """Create a property with condition to check for line item inserts."""
        return 'namespace'

    def process(self):
        """Process usage report file.

        Returns:
            (None)

        """
        row_count = 0
        report_period_id = None
        opener, mode = self._get_file_opener(self._compression)

        with opener(self._report_path, mode) as f:
            LOG.info('File %s opened for processing', str(f))
            reader = csv.DictReader(f)
            for row in reader:
                if report_period_id is None:
                    report_period_id = self._create_report_period(row, self._cluster_id)
                report_id = self._create_report(row, report_period_id)
                self._create_usage_report_line_item(row, report_period_id, report_id)

                if len(self.processed_report.line_items) >= self._batch_size:
                    self._save_to_db()

                    self.report_db.merge_temp_table(
                        OCP_REPORT_TABLE_MAP['line_item'],
                        self.temp_table,
                        self.line_item_columns,
                        self.line_item_condition_column,
                        self.line_item_conflict_columns
                    )

                    LOG.info('Saving report rows %d to %d for %s', row_count,
                             row_count + len(self.processed_report.line_items),
                             self._report_name)
                    row_count += len(self.processed_report.line_items)

                    self._update_mappings()

            if self.processed_report.line_items:
                self._save_to_db()

                self.report_db.merge_temp_table(
                    OCP_REPORT_TABLE_MAP['line_item'],
                    self.temp_table,
                    self.line_item_columns,
                    self.line_item_condition_column,
                    self.line_item_conflict_columns
                )

                LOG.info('Saving report rows %d to %d for %s', row_count,
                         row_count + len(self.processed_report.line_items),
                         self._report_name)

                row_count += len(self.processed_report.line_items)

            self.report_db.close_session()
            self.report_db.close_connections()

        LOG.info('Completed report processing for file: %s and schema: %s',
                 self._report_path, self._schema_name)

    def update_summary_tables(self, start_date, end_date=None):
        """Populate the summary tables for reporting.

        Args:
            start_date (String) The date to start populating the table.
            end_date   (String) The date to end on.

        Returns
            None

        """
        LOG.info('Updating report summary tables for %s from %s to %s',
                 self._schema_name, start_date, end_date)
