"""Test for the CostModels model."""
import logging
import random
from unittest.mock import patch
from uuid import UUID

from api.iam.models import Tenant
from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from faker import Faker
from masu.test import MasuTestCase
from tenant_schemas.utils import tenant_context

FAKE = Faker()


class CostModelTest(MasuTestCase):
    """Test cases for the CostModel model."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        if not getattr(cls, "tenant", None):
            cls.tenant = Tenant.objects.get_or_create(schema_name=cls.schema)[0]

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

    @patch("masu.processor.tasks.update_charge_info")
    def test_delete_cost_model_instance(self, mock_update_charge_info):
        """Assert the update_charge_info task is called on instance delete."""
        with tenant_context(self.tenant):
            self.cost_model.delete()
        mock_update_charge_info.delay.assert_called_with(self.schema, UUID(self.aws_provider_uuid))

    @patch("masu.processor.tasks.update_charge_info")
    def test_delete_cost_model_instance_skips_task_if_provider_has_no_customers(self, mock_update_charge_info):
        """Assert the update_charge_info task is not called if Customer is None."""
        with tenant_context(self.tenant), self.assertLogs("cost_models.models", "WARNING") as captured_logs:
            self.aws_provider.customer = None
            self.aws_provider.save()
            self.cost_model.delete()
        mock_update_charge_info.delay.assert_not_called()
        self.assertIn("has no Customer", captured_logs.output[0])

    @patch("masu.processor.tasks.update_charge_info")
    def test_delete_cost_model_instance_skips_task_if_provider_uuid_invalid(self, mock_update_charge_info):
        """Assert the update_charge_info task is not called if the provider uuid is invalid."""
        with tenant_context(self.tenant), self.assertLogs("cost_models.models", "WARNING") as captured_logs:
            self.cost_model_map.provider_uuid = FAKE.uuid4()
            self.cost_model_map.save()
            self.cost_model.delete()
        mock_update_charge_info.delay.assert_not_called()
        self.assertIn("invalid provider id", captured_logs.output[0])

    @patch("masu.processor.tasks.update_charge_info")
    def test_delete_cost_model_instance_skips_task_if_cost_model_map_does_not_exist(self, mock_update_charge_info):
        """Assert the update_charge_info task is not called if a cost_model_map does not exist."""
        with tenant_context(self.tenant):
            self.cost_model_map.delete()
            self.cost_model.delete()
        mock_update_charge_info.delay.assert_not_called()
