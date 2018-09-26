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

import gzip
import logging

from masu.external import GZIP_COMPRESSED
from masu.processor.report_processor_base import ReportProcessorBase

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods, no-self-use, duplicate-code
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

    def remove_temp_cur_files(self, report_path):
        """Remove temporary cost usage report files."""

    def process(self):
        """Process CUR file.

        Returns:
            (None)

        """
        opener, mode = self._get_file_opener(self._compression)
        # pylint: disable=invalid-name
        with opener(self._report_path, mode) as f:
            LOG.info('File %s opened for processing', str(f))

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
