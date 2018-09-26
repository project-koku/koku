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
from masu.exceptions import MasuProcessingError
from masu.processor import ALLOWED_COMPRESSIONS


# pylint: disable=too-few-public-methods
class ReportProcessorBase():
    """
    Download cost reports from a provider.

    Base object class for downloading cost reports from a cloud provider.
    """

    def __init__(self, schema_name, report_path, compression):
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
