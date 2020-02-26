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
"""Test the ReportChargeUpdater object."""
from unittest.mock import patch

from masu.processor.aws.aws_cost_model_cost_updater import AWSCostModelCostUpdater
from masu.processor.azure.azure_cost_model_cost_updater import AzureCostModelCostUpdater
from masu.processor.cost_model_cost_updater import ReportChargeUpdater
from masu.processor.cost_model_cost_updater import ReportChargeUpdaterError
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.test import MasuTestCase


class ReportChargeUpdaterTest(MasuTestCase):
    """Test class for the report summary updater."""

    @patch("masu.processor.cost_model_cost_updater.OCPCostModelCostUpdater.update_summary_charge_info")
    def test_ocp_route(self, mock_update):
        """Test that OCP charge updating works as expected."""
        updater = ReportChargeUpdater(self.schema, self.ocp_test_provider_uuid)
        self.assertIsInstance(updater._updater, OCPCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.AzureCostModelCostUpdater.update_summary_charge_info")
    def test_azure_local_route(self, mock_update):
        """Test that AZURE-local charge updating works as expected."""
        updater = ReportChargeUpdater(self.schema, self.azure_test_provider_uuid)
        self.assertIsInstance(updater._updater, AzureCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.AWSCostModelCostUpdater.update_summary_charge_info")
    def test_aws_route(self, mock_update):
        """Test that AWS charge updating works as expected."""
        updater = ReportChargeUpdater(self.schema, self.aws_provider_uuid)
        self.assertIsInstance(updater._updater, AWSCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.AzureCostModelCostUpdater.update_summary_charge_info")
    def test_azure_route(self, mock_update):
        """Test that Azure charge updating works as expected."""
        updater = ReportChargeUpdater(self.schema, self.azure_test_provider_uuid)
        self.assertIsInstance(updater._updater, AzureCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.OCPCostModelCostUpdater.__init__")
    def test_init_fail(self, mock_updater):
        """Test that an unimplemented provider throws an error."""
        mock_updater.side_effect = Exception("general error")

        with self.assertRaises(ReportChargeUpdaterError):
            ReportChargeUpdater(self.schema, self.ocp_test_provider_uuid)

    @patch("masu.processor.cost_model_cost_updater.ProviderDBAccessor.get_provider", return_value=None)
    def test_unknown_provider(self, mock_accessor):
        """Test no exception when initializing unknown provider."""
        try:
            ReportChargeUpdater(self.schema, self.unkown_test_provider_uuid)
        except Exception as err:
            self.fail(f"Failed with exception: {err}")
