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

"""Test the AzureReportDBCleaner object."""
from masu.processor.azure.azure_report_db_cleaner import AzureReportDBCleaner
from masu.test import MasuTestCase


class AzureReportDBCleanerTest(MasuTestCase):
    """Test Cases for the AzureReportChargeUpdater object."""

    def setUp(self):
        """Set up each test."""
        super().setUp()

        self.cleaner = AzureReportDBCleaner(
            schema=self.schema)

    def test_purge_expired_report_data(self):
        """Test to verify that expired Azure report data is cleared."""
        self.cleaner.purge_expired_report_data()
