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
"""Test the AzureCostModelCostUpdater object."""
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.azure.azure_cost_model_cost_updater import AzureCostModelCostUpdater
from masu.test import MasuTestCase
from reporting_common import REPORT_COLUMN_MAP


class AzureCostModelCostUpdaterTest(MasuTestCase):
    """Test Cases for the AzureCostModelCostUpdater object."""

    def test_azure_update_summary_cost_model_costs(self):
        """Test to verify Azure derived cost summary is calculated."""
        updater = AzureCostModelCostUpdater(schema=self.schema, provider=self.azure_provider)
        start_date = DateAccessor().today_with_timezone("UTC")
        bill_date = start_date.replace(day=1).date()

        updater.update_summary_cost_model_costs()

        column_map = REPORT_COLUMN_MAP

        with AzureReportDBAccessor(self.schema, column_map) as accessor:
            bill = accessor.get_cost_entry_bills_by_date(bill_date)[0]
            self.assertIsNotNone(bill.derived_cost_datetime)
