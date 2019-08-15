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

"""Test the AzureReportProcessor object."""
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.azure.azure_report_processor import AzureReportProcessor
from masu.external import GZIP_COMPRESSED, UNCOMPRESSED

from masu.test import MasuTestCase


class AzureReportProcessorTest(MasuTestCase):
    """Test Cases for the AzureReportProcessor object."""

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.test_report = './koku/masu/test/data/test_cur.csv'
        self.processor = AzureReportProcessor(
            schema_name=self.schema,
            report_path=self.test_report,
            compression=UNCOMPRESSED,
            provider_id=self.azure_provider_id,
        )

    def test_process(self):
        """Test process method."""
        self.processor.process()

    def test_remove_temp_cur_files(self):
        """Test verify temporary files are removed."""
        self.processor.remove_temp_cur_files(self.test_report)
