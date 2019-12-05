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
"""Test the Cost Model Manager."""

from tenant_schemas.utils import tenant_context

from api.iam.models import Customer
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.metrics.models import CostModelMetricsMap
from api.provider.models import Provider
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModel, CostModelMap


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
        self.customer = Customer.objects.get(
            account_id=self.customer_data['account_id']
        )
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            self.user = serializer.save()

    def tearDown(self):
        """Clean up database after test case."""
        with tenant_context(self.tenant):
            CostModel.objects.all().delete()
            CostModelMap.objects.all().delete()
            Provider.objects.all().delete()

    def test_create(self):
        """Test creating a cost model."""
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = 'OCP'
        tiered_rates = [{'unit': 'USD', 'value': 0.22}]
        data = {
            'name': 'Test Cost Model',
            'description': 'Test',
            'rates': [
                {
                    'metric': {'name': metric},
                    'source_type': source_type,
                    'tiered_rates': tiered_rates
                }
            ]
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            cost_model_obj = manager.create(**data)
            self.assertIsNotNone(cost_model_obj.uuid)
            for rate in cost_model_obj.rates:
                self.assertEqual(rate.get('metric', {}).get('name'), metric)
                self.assertEqual(rate.get('tiered_rates'), tiered_rates)
                self.assertEqual(rate.get('source_type'), source_type)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)
            self.assertEqual(CostModelManager(cost_model_obj.uuid).get_provider_names_uuids(), [])

    def test_create_with_provider(self):
        """Test creating a cost model with provider uuids."""
        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = 'OCP'
        tiered_rates = [{'unit': 'USD', 'value': 0.22}]
        data = {
            'name': 'Test Cost Model',
            'description': 'Test',
            'provider_uuids': [provider_uuid],
            'rates': [
                {
                    'metric': {'name': metric},
                    'source_type': source_type,
                    'tiered_rates': tiered_rates
                }
            ]
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            cost_model_obj = manager.create(**data)
            self.assertIsNotNone(cost_model_obj.uuid)
            for rate in cost_model_obj.rates:
                self.assertEqual(rate.get('metric', {}).get('name'), metric)
                self.assertEqual(rate.get('tiered_rates'), tiered_rates)
                self.assertEqual(rate.get('source_type'), source_type)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertIsNotNone(cost_model_map)
            self.assertEqual(cost_model_map.first().provider_uuid, provider_uuid)
            self.assertEqual(CostModelManager(cost_model_obj.uuid).get_provider_names_uuids(),
                             [{'uuid': str(provider_uuid), 'name': 'sample_provider'}])

    def test_create_second_cost_model_same_provider(self):
        """Test that the cost model map is updated for the second model."""
        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid
        provider_names_uuids = [{'uuid': str(provider.uuid), 'name': provider.name}]
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = 'OCP'
        tiered_rates = [{'unit': 'USD', 'value': 0.22}]
        data = {
            'name': 'Test Cost Model',
            'description': 'Test',
            'provider_uuids': [provider_uuid],
            'rates': [
                {
                    'metric': {'name': metric},
                    'source_type': source_type,
                    'tiered_rates': tiered_rates
                }
            ]
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            cost_model_obj = manager.create(**data)

            cost_model_map = CostModelMap.objects.filter(provider_uuid=provider_uuid)
            self.assertIsNotNone(cost_model_map)
            self.assertEqual(cost_model_map.first().cost_model, cost_model_obj)
            self.assertEqual(CostModelManager(cost_model_obj.uuid).get_provider_names_uuids(), provider_names_uuids)

            second_cost_model_obj = manager.create(**data)
            cost_model_map = CostModelMap.objects.filter(provider_uuid=provider_uuid)
            self.assertIsNotNone(cost_model_map)
            # Make sure we no longer associate this provider with
            # the previous cost model
            self.assertNotEqual(cost_model_map.first().cost_model, cost_model_obj)
            self.assertEqual(cost_model_map.first().cost_model, second_cost_model_obj)
            self.assertEqual(CostModelManager(second_cost_model_obj.uuid).get_provider_names_uuids(),
                             provider_names_uuids)

    def test_create_with_two_providers(self):
        """Test creating a cost model with multiple providers."""
        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        provider_name_2 = 'sample_provider2'
        provider_2 = Provider.objects.create(name=provider_name_2,
                                             created_by=self.user,
                                             customer=self.customer)
        provider_uuid_2 = provider_2.uuid

        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = 'OCP'
        tiered_rates = [{'unit': 'USD', 'value': 0.22}]
        data = {
            'name': 'Test Cost Model',
            'description': 'Test',
            'provider_uuids': [provider_uuid, provider_uuid_2],
            'rates': [
                {
                    'metric': {'name': metric},
                    'source_type': source_type,
                    'tiered_rates': tiered_rates
                }
            ]
        }

        with tenant_context(self.tenant):
            manager = CostModelManager()
            cost_model_obj = manager.create(**data)
            self.assertIsNotNone(cost_model_obj.uuid)
            for rate in cost_model_obj.rates:
                self.assertEqual(rate.get('metric', {}).get('name'), metric)
                self.assertEqual(rate.get('tiered_rates'), tiered_rates)
                self.assertEqual(rate.get('source_type'), source_type)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 2)
            self.assertEqual(CostModelMap.objects.get(provider_uuid=provider_uuid).cost_model, cost_model_obj)
            self.assertEqual(CostModelMap.objects.get(provider_uuid=provider_uuid_2).cost_model, cost_model_obj)

        # Remove Rate object and verify that the CostModelMap is updated to no longer contain the providers.
        with tenant_context(self.tenant):
            CostModel.objects.get(uuid=cost_model_obj.uuid).delete()
            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)

    def test_update_provider_uuids(self):
        """Test creating a cost model then update with a provider uuid."""
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        source_type = 'OCP'
        tiered_rates = [{'unit': 'USD', 'value': 0.22}]
        data = {
            'name': 'Test Cost Model',
            'description': 'Test',
            'rates': [
                {
                    'metric': {'name': metric},
                    'source_type': source_type,
                    'tiered_rates': tiered_rates
                }
            ]
        }
        cost_model_obj = None
        with tenant_context(self.tenant):
            manager = CostModelManager()
            cost_model_obj = manager.create(**data)

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)

        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        # Add provider to existing cost model
        with tenant_context(self.tenant):
            manager = CostModelManager(cost_model_uuid=cost_model_obj.uuid)
            manager.update_provider_uuids(provider_uuids=[provider_uuid])

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertIsNotNone(cost_model_map)
            self.assertEqual(cost_model_map.first().provider_uuid, provider_uuid)
            self.assertEqual(len(cost_model_map), 1)

        # Add provider again to existing cost model.  Verify there is still only 1 item in map
        with tenant_context(self.tenant):
            manager = CostModelManager(cost_model_uuid=cost_model_obj.uuid)
            manager.update_provider_uuids(provider_uuids=[provider_uuid])

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertIsNotNone(cost_model_map)
            self.assertEqual(cost_model_map.first().provider_uuid, provider_uuid)
            self.assertEqual(len(cost_model_map), 1)

        # Remove provider from existing rate
        with tenant_context(self.tenant):
            manager = CostModelManager(cost_model_uuid=cost_model_obj.uuid)
            manager.update_provider_uuids(provider_uuids=[])

            cost_model_map = CostModelMap.objects.filter(cost_model=cost_model_obj)
            self.assertEqual(len(cost_model_map), 0)
