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

"""Test the AzureReportChargeUpdater object."""
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.azure.azure_report_charge_updater import AzureReportChargeUpdater
from masu.test import MasuTestCase


class AzureReportChargeUpdaterTest(MasuTestCase):
    """Test Cases for the AzureReportChargeUpdater object."""

    def setUp(self):
        """Set up each test."""
        super().setUp()

        self.provider_accessor = ProviderDBAccessor(
            provider_uuid=self.azure_test_provider_uuid
        )
        provider_id = self.provider_accessor.get_provider().id

        self.updater = AzureReportChargeUpdater(
            schema=self.schema,
            provider_uuid=self.azure_test_provider_uuid,
            provider_id=provider_id)

    def test_update_summary_charge_info(self):
        """Test to verify Azure derived cost summary is calculated."""
        self.updater.update_summary_charge_info()
