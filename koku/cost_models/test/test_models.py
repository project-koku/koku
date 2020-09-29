"""Test for the CostModels model."""
import logging
import random

from django_tenants.utils import tenant_context
from faker import Faker

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

    def test_delete_cost_model_instance(self):
        """Assert the update_cost_model_costs task is called on instance delete."""
        with tenant_context(self.tenant):
            self.cost_model.delete()
            # We aren't running transactional test cases, so we can't test commit hooks
            self.assertEqual(CostModelMap.objects.count(), 0)
