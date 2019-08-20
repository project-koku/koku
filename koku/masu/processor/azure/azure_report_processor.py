#
# Copyright 2019 Red Hat, Inc.
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

"""Processor for Azure Cost Usage Reports."""

import logging

from masu.processor.report_processor_base import ReportProcessorBase


LOG = logging.getLogger(__name__)


# pylint: disable=too-many-instance-attributes
class AzureReportProcessor(ReportProcessorBase):
    """Cost Usage Report processor."""

    # pylint:disable=too-many-arguments
    def __init__(self, schema_name, report_path, compression, provider_id, manifest_id=None):
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
            provider_id=provider_id
        )

        self.manifest_id = manifest_id
        self._report_name = report_path
        self._schema_name = schema_name
        LOG.info('Initialized report processor for file: %s and schema: %s',
                 self._report_name, self._schema_name)

    def process(self):
        """Process CUR file.

        Returns:
            (None)

        """
        pass

    # pylint: disable=no-self-use
    def remove_temp_cur_files(self, report_path):
        """Remove temporary report files."""
        pass
