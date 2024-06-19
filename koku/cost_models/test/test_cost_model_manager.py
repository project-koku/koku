#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Cost Model Manager."""
from unittest.mock import patch

from django_tenants.utils import tenant_context

from api.iam.models import Customer
from api.iam.models import User
from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.provider.models import Provider
from common.queues import PriorityQueue
from cost_models.cost_model_manager import CostModelException
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModel
from cost_models.models import CostModelMap


class MockResponse:
    """A mock response that can convert response text to json."""

    def __init__(self, status_code, response_text):
        """Initialize the response."""
        self.status_code = status_code
        self.response_text = response_text


class CostModelManagerTest(IamTestCase):
    """Tests for Cost Model Manager."""

    def setUp(self):
        """Set up the cost model manager tests."""
        super().setUp()
        self.customer = Customer.objects.get(account_id=self.customer_data["account_id"])
        self.user = User.objects.get(username=self.user_data["username"])

    def test_create(self):
        """Test creating a cost model."""
        metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "rates": [{"metric": {"name": metric}, "source_type": source_type, "tiered_rates": tiered_rates}],
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                cost_model_obj = manager.create(**data)
            self.assertIsNotNone(cost_model_obj.uuid)
            for rate in cost_model_obj.rates:
                self.assertEqual(rate.get("metric", {}).get("name"), metric)
                self.assertEqual(rate.get("tiered_rates"), tiered_rates)
                self.assertEqual(rate.get("source_type"), source_type)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)
            self.assertEqual(CostModelManager(cost_model_obj.uuid).get_provider_names_uuids(), [])

    def test_create_with_provider(self):
        """Test creating a cost model with provider uuids."""
        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid
        metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "provider_uuids": [provider_uuid],
            "rates": [{"metric": {"name": metric}, "source_type": source_type, "tiered_rates": tiered_rates}],
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                cost_model_obj = manager.create(**data)
                mock_update.s.return_value.set.return_value.apply_async.assert_called()
            self.assertIsNotNone(cost_model_obj.uuid)
            for rate in cost_model_obj.rates:
                self.assertEqual(rate.get("metric", {}).get("name"), metric)
                self.assertEqual(rate.get("tiered_rates"), tiered_rates)
                self.assertEqual(rate.get("source_type"), source_type)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertIsNotNone(cost_model_map)
            self.assertEqual(cost_model_map.first().provider_uuid, provider_uuid)
            self.assertEqual(
                CostModelManager(cost_model_obj.uuid).get_provider_names_uuids(),
                [{"uuid": str(provider_uuid), "name": "sample_provider", "last_processed": None}],
            )

    def test_create_second_cost_model_same_provider(self):
        """Test that the cost model map is updated for the second model."""
        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid
        provider_names_uuids = [
            {"uuid": str(provider.uuid), "name": provider.name, "last_processed": provider.data_updated_timestamp}
        ]
        metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "provider_uuids": [provider_uuid],
            "rates": [{"metric": {"name": metric}, "source_type": source_type, "tiered_rates": tiered_rates}],
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                cost_model_obj = manager.create(**data)
                mock_update.s.return_value.set.return_value.apply_async.assert_called()

            cost_model_map = CostModelMap.objects.filter(provider_uuid=provider_uuid)
            self.assertIsNotNone(cost_model_map)
            self.assertEqual(cost_model_map.first().cost_model, cost_model_obj)
            self.assertEqual(CostModelManager(cost_model_obj.uuid).get_provider_names_uuids(), provider_names_uuids)

            second_cost_model_obj = None
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                with self.assertRaises(CostModelException):
                    second_cost_model_obj = manager.create(**data)
            cost_model_map = CostModelMap.objects.filter(provider_uuid=provider_uuid)
            self.assertIsNotNone(cost_model_map)
            # Make sure we still associate this provider with the previous cost model.
            self.assertEqual(cost_model_map.first().cost_model, cost_model_obj)

            # Make sure second cost model was never created.
            self.assertIsNone(second_cost_model_obj)

    def test_create_with_two_providers(self):
        """Test creating a cost model with multiple providers."""
        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        provider_name_2 = "sample_provider2"
        with patch("masu.celery.tasks.check_report_updates"):
            provider_2 = Provider.objects.create(name=provider_name_2, created_by=self.user, customer=self.customer)
        provider_uuid_2 = provider_2.uuid

        metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "provider_uuids": [provider_uuid, provider_uuid_2],
            "rates": [{"metric": {"name": metric}, "source_type": source_type, "tiered_rates": tiered_rates}],
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                cost_model_obj = manager.create(**data)
                mock_update.s.return_value.set.return_value.apply_async.assert_called()
            self.assertIsNotNone(cost_model_obj.uuid)
            for rate in cost_model_obj.rates:
                self.assertEqual(rate.get("metric", {}).get("name"), metric)
                self.assertEqual(rate.get("tiered_rates"), tiered_rates)
                self.assertEqual(rate.get("source_type"), source_type)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 2)
            self.assertEqual(CostModelMap.objects.get(provider_uuid=provider_uuid).cost_model, cost_model_obj)
            self.assertEqual(CostModelMap.objects.get(provider_uuid=provider_uuid_2).cost_model, cost_model_obj)

        # Remove Rate object and verify that the CostModelMap is updated to no longer contain the providers.
        with tenant_context(self.tenant):
            CostModel.objects.get(uuid=cost_model_obj.uuid).delete()
            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)

    def test_update_provider_uuids_with_XL_queue(self):
        """Test creating a cost model with XL queue."""
        metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "rates": [{"metric": {"name": metric}, "source_type": source_type, "tiered_rates": tiered_rates}],
        }
        cost_model_obj = None
        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                cost_model_obj = manager.create(**data)
                mock_update.s.return_value.set.return_value.apply_async.assert_not_called()

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)

        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        # Add provider to existing cost model
        with tenant_context(self.tenant):
            manager = CostModelManager(cost_model_uuid=cost_model_obj.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                with patch("cost_models.cost_model_manager.get_customer_queue", return_value=PriorityQueue.XL):
                    manager.update_provider_uuids(provider_uuids=[provider_uuid])
                    mock_update.s.return_value.set.assert_called_with(queue=PriorityQueue.XL)

    def test_update_provider_uuids(self):
        """Test creating a cost model then update with a provider uuid."""
        metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "rates": [{"metric": {"name": metric}, "source_type": source_type, "tiered_rates": tiered_rates}],
        }
        cost_model_obj = None
        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                cost_model_obj = manager.create(**data)
                mock_update.s.return_value.set.return_value.apply_async.assert_not_called()

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)

        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        # Add provider to existing cost model
        with tenant_context(self.tenant):
            manager = CostModelManager(cost_model_uuid=cost_model_obj.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                manager.update_provider_uuids(provider_uuids=[provider_uuid])
                mock_update.s.return_value.set.return_value.apply_async.assert_called()

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertIsNotNone(cost_model_map)
            self.assertEqual(cost_model_map.first().provider_uuid, provider_uuid)
            self.assertEqual(len(cost_model_map), 1)

        # Add provider again to existing cost model.  Verify there is still only 1 item in map
        with tenant_context(self.tenant):
            manager = CostModelManager(cost_model_uuid=cost_model_obj.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                manager.update_provider_uuids(provider_uuids=[provider_uuid])
                mock_update.s.return_value.set.return_value.apply_async.assert_called()

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertIsNotNone(cost_model_map)
            self.assertEqual(cost_model_map.first().provider_uuid, provider_uuid)
            self.assertEqual(len(cost_model_map), 1)

        # Remove provider from existing rate
        with tenant_context(self.tenant):
            manager = CostModelManager(cost_model_uuid=cost_model_obj.uuid)
            with patch("cost_models.cost_model_manager.update_cost_model_costs") as mock_update:
                manager.update_provider_uuids(provider_uuids=[])
                mock_update.s.return_value.set.return_value.apply_async.assert_called()

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)

    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_deleting_cost_model_triggers_tasks(self, mock_update):
        """Test deleting a cost model refreshes the materialized views."""
        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "provider_uuids": [provider_uuid],
            "markup": {"value": 10, "unit": "percent"},
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            cost_model_obj = manager.create(**data)
            self.assertIsNotNone(cost_model_obj.uuid)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertIsNotNone(cost_model_map)

            # simulates deleting a cost_model
            manager.update_provider_uuids(provider_uuids=[])
            mock_update.s.return_value.set.return_value.apply_async.assert_called()

    @patch("cost_models.cost_model_manager.update_cost_model_costs")
    def test_deleting_cost_model_not_triggers_tasks(self, mock_update):
        """Test deleting a cost model with an inactive provider does not trigger tasks."""
        provider_name = "sample_provider"
        with patch("masu.celery.tasks.check_report_updates"):
            provider = Provider.objects.create(name=provider_name, created_by=self.user, customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid
        provider.active = False
        provider.save()

        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "provider_uuids": [provider_uuid],
            "markup": {"value": 10, "unit": "percent"},
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                cost_model_obj = manager.create(**data)
            self.assertIsNotNone(cost_model_obj.uuid)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertIsNotNone(cost_model_map)

            # simulates deleting a cost_model
            manager.update_provider_uuids(provider_uuids=[])
            mock_update.assert_not_called()

    def test_update_distribution_choice(self):
        """Test creating a cost model."""
        metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        distribution = "memory"
        update_distribution = "cpu"
        data = {
            "name": "Test Cost Model",
            "description": "Test",
            "rates": [{"metric": {"name": metric}, "source_type": source_type, "tiered_rates": tiered_rates}],
            "distribution": distribution,
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                cost_model_obj = manager.create(**data)
            self.assertIsNotNone(cost_model_obj.uuid)
            self.assertEqual(cost_model_obj.distribution, distribution)
            for rate in cost_model_obj.rates:
                self.assertEqual(rate.get("metric", {}).get("name"), metric)
                self.assertEqual(rate.get("tiered_rates"), tiered_rates)
                self.assertEqual(rate.get("source_type"), source_type)
            data["distribution"] = update_distribution
            with patch("cost_models.cost_model_manager.update_cost_model_costs"):
                cost_model_obj = manager.update(**data)
                self.assertEqual(manager.instance.distribution, update_distribution)
