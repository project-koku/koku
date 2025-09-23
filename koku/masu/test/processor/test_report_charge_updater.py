#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the CostModelCostUpdater object."""
from unittest.mock import patch

from masu.processor.aws.aws_cost_model_cost_updater import AWSCostModelCostUpdater
from masu.processor.azure.azure_cost_model_cost_updater import AzureCostModelCostUpdater
from masu.processor.cost_model_cost_updater import CostModelCostUpdater
from masu.processor.cost_model_cost_updater import CostModelCostUpdaterError
from masu.processor.gcp.gcp_cost_model_cost_updater import GCPCostModelCostUpdater
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.test import MasuTestCase


class CostModelCostUpdaterTest(MasuTestCase):
    """Test class for the report summary updater."""

    @patch("masu.processor.cost_model_cost_updater.OCPCostModelCostUpdater.update_summary_cost_model_costs")
    def test_ocp_route(self, mock_update):
        """Test that OCP charge updating works as expected."""
        updater = CostModelCostUpdater(self.schema, self.ocp_test_provider_uuid)
        self.assertIsInstance(updater._updater, OCPCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.AzureCostModelCostUpdater.update_summary_cost_model_costs")
    def test_azure_local_route(self, mock_update):
        """Test that AZURE-local charge updating works as expected."""
        updater = CostModelCostUpdater(self.schema, self.azure_test_provider_uuid)
        self.assertIsInstance(updater._updater, AzureCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.AWSCostModelCostUpdater.update_summary_cost_model_costs")
    def test_aws_route(self, mock_update):
        """Test that AWS charge updating works as expected."""
        updater = CostModelCostUpdater(self.schema, self.aws_provider_uuid)
        self.assertIsInstance(updater._updater, AWSCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.GCPCostModelCostUpdater.update_summary_cost_model_costs")
    def test_gcp_route(self, mock_update):
        """Test that AWS charge updating works as expected."""
        updater = CostModelCostUpdater(self.schema, self.gcp_provider_uuid)
        self.assertIsInstance(updater._updater, GCPCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.AzureCostModelCostUpdater.update_summary_cost_model_costs")
    def test_azure_route(self, mock_update):
        """Test that Azure charge updating works as expected."""
        updater = CostModelCostUpdater(self.schema, self.azure_test_provider_uuid)
        self.assertIsInstance(updater._updater, AzureCostModelCostUpdater)
        updater.update_cost_model_costs()
        mock_update.assert_called()

    @patch("masu.processor.cost_model_cost_updater.OCPCostModelCostUpdater.__init__")
    def test_init_fail(self, mock_updater):
        """Test that an unimplemented provider throws an error."""
        mock_updater.side_effect = Exception("general error")

        with self.assertRaises(CostModelCostUpdaterError):
            CostModelCostUpdater(self.schema, self.ocp_test_provider_uuid)

    def test_unknown_provider(self):
        """Test no exception when initializing unknown provider."""
        try:
            updater = CostModelCostUpdater(self.schema, self.unkown_test_provider_uuid)
        except Exception as err:
            self.fail(f"Failed with exception: {err}")
        self.assertIsNone(updater._updater)

    def test_updater_is_none_if_setup_not_complete(self):
        """
        Test that the internal updater is not set if provider setup is not complete.
        """
        provider = self.aws_provider
        provider.setup_complete = False
        provider.save()
        with self.assertLogs("masu.processor.cost_model_cost_updater", level="DEBUG") as logger:
            updater = CostModelCostUpdater(self.schema, provider.uuid)
            self.assertIsNone(updater._updater)
            self.assertIn("Provider setup is not complete", str(logger.output))
