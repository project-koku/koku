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
"""Report Processor base class."""
import csv
import gzip
import io
import json
import logging
from os import listdir

from masu.exceptions import MasuProcessingError
from masu.external import GZIP_COMPRESSED
from masu.processor import ALLOWED_COMPRESSIONS
from masu.util.common import clear_temp_directory

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ReportProcessorBase():
    """
    Download cost reports from a provider.

    Base object class for downloading cost reports from a cloud provider.
    """

    def __init__(self, schema_name, report_path, compression, provider_id, processed_report):
        """Initialize the report processor base class.

        Args:
            schema_name (str): The name of the customer schema to process into
            report_path (str): Where the report file lives in the file system
            compression (CONST): How the report file is compressed.
                Accepted values: UNCOMPRESSED, GZIP_COMPRESSED

        """
        if compression.upper() not in ALLOWED_COMPRESSIONS:
            err_msg = f'Compression {compression} is not supported.'
            raise MasuProcessingError(err_msg)

        self._schema_name = schema_name
        self._report_path = report_path
        self._compression = compression.upper()
        self._provider_id = provider_id
        self.processed_report = processed_report

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

    @staticmethod
    def _get_file_opener(compression):
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

    def _save_to_db(self, temp_table, report_db_accessor):
        """Save current batch of records to the database."""
        columns = tuple(self.processed_report.line_items[0].keys())
        csv_file = self._write_processed_rows_to_csv()

        report_db_accessor.commit()

        report_db_accessor.bulk_insert_rows(
            csv_file,
            temp_table,
            columns)

    @staticmethod
    def remove_temp_cur_files(report_path):
        """Remove temporary report files."""
        LOG.info('Cleaning up temporary report files for %s', report_path)
        current_assembly_id = None
        files = listdir(report_path)
        for file in files:
            file_path = '{}/{}'.format(report_path, file)
            if file.endswith('Manifest.json'):
                with open(file_path, 'r') as manifest_file_handle:
                    manifest_json = json.load(manifest_file_handle)
                    current_assembly_id = manifest_json.get('assemblyId')

        removed_files = []
        if current_assembly_id:
            removed_files = clear_temp_directory(report_path, current_assembly_id)

        return removed_files
