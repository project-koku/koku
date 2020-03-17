"""Test for the CostModels model."""
import logging
import random
from unittest.mock import patch

from faker import Faker
from tenant_schemas.utils import tenant_context

from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from masu.test import MasuTestCase

FAKE = Faker()


class CostModelTest(MasuTestCase):
    """Test cases for the CostModel model."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        # Must set this to capture the logger messages in the tests.
        logging.disable(0)

    def setUp(self):
        """Set up the shared variables for each test case."""
        super().setUp()
        with tenant_context(self.tenant):
            self.cost_model = CostModel.objects.create(
                name=FAKE.word(), description=FAKE.word(), source_type=random.choice(Provider.PROVIDER_CHOICES)
            )
            self.cost_model_map = CostModelMap.objects.create(
                cost_model=self.cost_model, provider_uuid=self.aws_provider_uuid
            )

    @patch("cost_models.models.cost_model_pre_delete_callback")
    def test_delete_cost_model_instance(self, mock_update_cost_model_costs):
        """Assert the update_cost_model_costs task is called on instance delete."""
        with tenant_context(self.tenant):
            self.cost_model.delete()
            # We aren't running transactional test cases, so we can't test commit hooks
            self.assertEqual(CostModelMap.objects.count(), 0)

    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_delete_cost_model_instance_skips_task_if_provider_has_no_customers(self, mock_update_cost_model_costs):
        """Assert the update_cost_model_costs task is not called if Customer is None."""
        with tenant_context(self.tenant), self.assertLogs("cost_models.models", "WARNING") as captured_logs:
            self.aws_provider.customer = None
            self.aws_provider.save()
            self.cost_model.delete()
        mock_update_cost_model_costs.delay.assert_not_called()
        self.assertIn("has no Customer", captured_logs.output[0])

    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_delete_cost_model_instance_skips_task_if_provider_uuid_invalid(self, mock_update_cost_model_costs):
        """Assert the update_cost_model_costs task is not called if the provider uuid is invalid."""
        with tenant_context(self.tenant), self.assertLogs("cost_models.models", "WARNING") as captured_logs:
            self.cost_model_map.provider_uuid = FAKE.uuid4()
            self.cost_model_map.save()
            self.cost_model.delete()
        mock_update_cost_model_costs.delay.assert_not_called()
        self.assertIn("invalid provider id", captured_logs.output[0])

    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_delete_cost_model_instance_skips_task_if_cost_model_map_does_not_exist(
        self, mock_update_cost_model_costs
    ):
        """Assert the update_cost_model_costs task is not called if a cost_model_map does not exist."""
        with tenant_context(self.tenant):
            self.cost_model_map.delete()
            self.cost_model.delete()
        mock_update_cost_model_costs.delay.assert_not_called()
