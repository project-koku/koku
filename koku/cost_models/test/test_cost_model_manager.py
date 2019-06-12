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
"""Test the Rate Manager."""

from tenant_schemas.utils import tenant_context

from api.iam.models import Customer
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.metrics.models import CostModelMetricsMap
from api.provider.models import Provider
from cost_models.models import Rate, RateMap
from cost_models.cost_model_manager import CostModelManager, CostModelManagerError


class MockResponse:
    """A mock response that can convert response text to json."""

    def __init__(self, status_code, response_text):
        """Initialize the response."""
        self.status_code = status_code
        self.response_text = response_text


class CostModelManagerTest(IamTestCase):
    """Tests for Rate Manager."""

    def setUp(self):
        """Set up the provider manager tests."""
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
            Rate.objects.all().delete()
            RateMap.objects.all().delete()
            Provider.objects.all().delete()

    def test_create(self):
        """Test creating a rate."""
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        rates = {'tiered_rate': [{'unit': 'USD', 'value': 0.22}]}

        with tenant_context(self.tenant):
            manager = CostModelManager()
            rate_obj = manager.create(metric=metric,
                                      rates=rates)
            self.assertEqual(rate_obj.metric, metric)
            self.assertEqual(rate_obj.rates, rates)
            self.assertIsNotNone(rate_obj.uuid)

            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertEqual(len(rate_map), 0)
            self.assertEqual(CostModelManager(rate_obj.uuid).get_provider_uuids(), [])

    def test_create_with_provider(self):
        """Test creating a rate with provider."""
        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        rates = {'tiered_rate': [{'unit': 'USD', 'value': 0.22}]}

        with tenant_context(self.tenant):
            manager = CostModelManager()
            rate_obj = manager.create(metric=metric,
                                      rates=rates,
                                      provider_uuids=[provider_uuid])
            self.assertEqual(rate_obj.metric, metric)
            self.assertEqual(rate_obj.rates, rates)
            self.assertIsNotNone(rate_obj.uuid)

            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertIsNotNone(rate_map)
            self.assertEqual(rate_map.first().provider_uuid, provider_uuid)
            self.assertEqual(CostModelManager(rate_obj.uuid).get_provider_uuids(), [provider_uuid])

    def test_create_with_provider_duplicates(self):
        """Test creating with duplicate rates for a provider."""
        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        rates = {'tiered_rate': [{'unit': 'USD', 'value': 0.22}]}

        with tenant_context(self.tenant):
            manager = CostModelManager()
            rate_obj = manager.create(metric=metric,
                                      rates=rates,
                                      provider_uuids=[provider_uuid])
            self.assertEqual(rate_obj.metric, metric)
            self.assertEqual(rate_obj.rates, rates)
            self.assertIsNotNone(rate_obj.uuid)

            with self.assertRaises(CostModelManagerError):
                manager.create(metric=metric,
                               rates=rates,
                               provider_uuids=[provider_uuid])

    def test_create_with_two_providers(self):
        """Test creating with rate with multiple providers."""
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
        rates = {'tiered_rate': [{'unit': 'USD', 'value': 0.22}]}

        with tenant_context(self.tenant):
            manager = CostModelManager()
            rate_obj = manager.create(metric=metric,
                                      rates=rates,
                                      provider_uuids=[provider_uuid, provider_uuid_2])
            self.assertEqual(rate_obj.metric, metric)
            self.assertEqual(rate_obj.rates, rates)
            self.assertIsNotNone(rate_obj.uuid)

            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertEqual(len(rate_map), 2)
            self.assertEqual(RateMap.objects.get(provider_uuid=provider_uuid).rate_id, rate_obj.id)
            self.assertEqual(RateMap.objects.get(provider_uuid=provider_uuid_2).rate_id, rate_obj.id)

        # Remove Rate object and verify that the RateMap is updated to no longer contain the providers.
        with tenant_context(self.tenant):
            Rate.objects.get(id=rate_obj.id).delete()
            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertEqual(len(rate_map), 0)

    def test_update_provider_uuids(self):
        """Test creating a rate then update with a provider uuid."""
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        rates = {'tiered_rate': [{'unit': 'USD', 'value': 0.22}]}

        rate_obj = None
        with tenant_context(self.tenant):
            manager = CostModelManager()
            rate_obj = manager.create(metric=metric,
                                      rates=rates)
            self.assertEqual(rate_obj.metric, metric)
            self.assertEqual(rate_obj.rates, rates)
            self.assertIsNotNone(rate_obj.uuid)

            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertEqual(len(rate_map), 0)

        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid

        # Add provider to existing rate
        with tenant_context(self.tenant):
            manager = CostModelManager(rate_uuid=rate_obj.uuid)
            manager.update_provider_uuids(provider_uuids=[provider_uuid])

            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertIsNotNone(rate_map)
            self.assertEqual(rate_map.first().provider_uuid, provider_uuid)
            self.assertEqual(len(rate_map), 1)

        # Add provider provider again to existing rate.  Verify there is still only 1 item in map
        with tenant_context(self.tenant):
            manager = CostModelManager(rate_uuid=rate_obj.uuid)
            manager.update_provider_uuids(provider_uuids=[provider_uuid])

            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertIsNotNone(rate_map)
            self.assertEqual(rate_map.first().provider_uuid, provider_uuid)
            self.assertEqual(len(rate_map), 1)

        # Remove provider from existing rate
        with tenant_context(self.tenant):
            manager = CostModelManager(rate_uuid=rate_obj.uuid)
            manager.update_provider_uuids(provider_uuids=[])

            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertEqual(len(rate_map), 0)

    def test_update_provider_uuids_duplicate_metric(self):
        """Test updating a rate with a metric colision for a provider."""
        provider_name = 'sample_provider'
        provider = Provider.objects.create(name=provider_name,
                                           created_by=self.user,
                                           customer=self.customer)

        # Get Provider UUID
        provider_uuid = provider.uuid
        metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        rates = {'tiered_rate': [{'unit': 'USD', 'value': 0.22}]}

        with tenant_context(self.tenant):
            manager = CostModelManager()
            rate_obj = manager.create(metric=metric,
                                      rates=rates,
                                      provider_uuids=[provider_uuid])
            self.assertEqual(rate_obj.metric, metric)
            self.assertEqual(rate_obj.rates, rates)
            self.assertIsNotNone(rate_obj.uuid)

            rate_map = RateMap.objects.filter(rate=rate_obj.id)
            self.assertIsNotNone(rate_map)
            self.assertEqual(rate_map.first().provider_uuid, provider_uuid)
            self.assertEqual(CostModelManager(rate_obj.uuid).get_provider_uuids(), [provider_uuid])

        # Create another rate with same metric
        rates_2 = {'tiered_rate': [{'unit': 'USD', 'value': 0.52}]}

        with tenant_context(self.tenant):
            manager_2 = CostModelManager()
            rate_obj_2 = manager_2.create(metric=metric, rates=rates_2)
            rate_map = RateMap.objects.filter(rate=rate_obj_2.id)
            self.assertIsNotNone(rate_map)
            self.assertEqual(len(rate_map), 0)

        # Update rate_2 with provider uuid that is already associated with another rate of same type
        with tenant_context(self.tenant):
            manager_3 = CostModelManager(rate_uuid=rate_obj_2.uuid)
            with self.assertRaises(CostModelManagerError):
                manager_3.update_provider_uuids(provider_uuids=[provider_uuid])
