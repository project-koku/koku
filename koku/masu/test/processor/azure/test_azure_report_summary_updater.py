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

"""Test the AzureReportSummaryUpdater object."""
from masu.processor.azure.azure_report_summary_updater import AzureReportSummaryUpdater

from masu.test import MasuTestCase


class AzureReportSummaryUpdaterTest(MasuTestCase):
    """Test Cases for the AzureReportSummaryUpdater object."""

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.updater = AzureReportSummaryUpdater(
           self.schema, self.azure_provider, None
        )


    def test_update_daily_tables(self):
        """Test process method."""
        self.updater.update_daily_tables(None, None)

    def test_update_summary_tables(self):
        """Test verify temporary files are removed."""
        self.updater.update_summary_tables(None, None)
