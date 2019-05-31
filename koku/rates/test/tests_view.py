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
"""Test the Rate views."""
import copy
import random
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import caches
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.models import User
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.metrics.models import CostModelMetricsMap
from api.provider.models import Provider
from api.provider.serializers import ProviderSerializer
from koku.rbac import RbacService
from rates.models import Rate, RateMap
from rates.serializers import RateSerializer


class RateViewTests(IamTestCase):
    """Test the Rate view."""

    def initialize_request(self, context=None):
        """Initialize model data."""
        if context:
            request_context = context.get('request_context')
            request = request_context['request']
            serializer = UserSerializer(data=context.get('user_data'), context=request_context)
        else:
            request_context = self.request_context
            request = request_context['request']
            serializer = UserSerializer(data=self.user_data, context=request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            request.user = user

        provider_data = {'name': 'test_provider',
                         'type': Provider.PROVIDER_OCP,
                         'authentication': {
                             'provider_resource_name': self.fake.word()
                         }}
        serializer = ProviderSerializer(data=provider_data, context=request_context)
        if serializer.is_valid(raise_exception=True):
            self.provider = serializer.save()

        self.fake_data = {'provider_uuids': [self.provider.uuid],
                          'metric': {'name': CostModelMetricsMap.OCP_METRIC_MEM_GB_USAGE_HOUR},
                          'tiered_rate': [{
                              'value': round(Decimal(random.random()), 6),
                              'unit': 'USD',
                              'usage': {'usage_start': None, 'usage_end': None}
                          }]
                          }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=self.fake_data, context=request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches['rbac'].clear()

        with tenant_context(self.tenant):
            Rate.objects.all().delete()
            RateMap.objects.all().delete()
            Provider.objects.all().delete()
            User.objects.all().delete()
        self.initialize_request()

    def tearDown(self):
        """Tear down rate view tests."""
        with tenant_context(self.tenant):
            Rate.objects.all().delete()
            RateMap.objects.all().delete()
            Provider.objects.all().delete()
            User.objects.all().delete()

    def test_create_rate_success(self):
        """Test that we can create a rate."""
        test_data = {'provider_uuids': [self.provider.uuid],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        # create a rate
        url = reverse('rates-list')
        client = APIClient()
        response = client.post(url, data=test_data, format='json', **self.headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # test that we can retrieve the rate
        url = reverse('rates-detail', kwargs={'uuid': response.data.get('uuid')})
        response = client.get(url, **self.headers)

        self.assertIsNotNone(response.data.get('uuid'))
        self.assertIsNotNone(response.data.get('provider_uuids'))
        self.assertEqual(test_data['metric']['name'], response.data.get('metric').get('name'))
        self.assertIsNotNone(response.data.get('tiered_rate'))

    def test_create_rate_invalid(self):
        """Test that creating an invalid rate returns an error."""
        test_data = {'name': self.fake.word(),
                     'provider_uuids': [],
                     'description': self.fake.text(),
                     'price': round(Decimal(random.random()), 6),
                     'timeunit': 'jiffy',
                     'metric': self.fake.word()}

        url = reverse('rates-list')
        client = APIClient()
        response = client.post(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_rate_success(self):
        """Test that we can read a rate."""
        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'uuid': rate.uuid})
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get('uuid'))
        self.assertIsNotNone(response.data.get('provider_uuids'))
        self.assertEqual(self.fake_data['metric']['name'], response.data.get('metric').get('name'))
        self.assertIsNotNone(response.data.get('tiered_rate'))

    def test_read_rate_invalid(self):
        """Test that reading an invalid rate returns an error."""
        url = reverse('rates-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_rate_success(self):
        """Test that we can update an existing rate."""
        test_data = self.fake_data
        test_data['tiered_rate'][0]['value'] = round(Decimal(random.random()), 6)

        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'uuid': rate.uuid})
        client = APIClient()
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIsNotNone(response.data.get('uuid'))
        self.assertEqual(test_data['tiered_rate'][0]['value'],
                         response.data.get('tiered_rate')[0].get('value'))
        self.assertEqual(test_data['metric']['name'], response.data.get('metric').get('name'))

    def test_update_rate_failure(self):
        """Test that we update fails with metric type duplication."""
        test_data = {'provider_uuids': [self.provider.uuid],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        # create a rate
        url = reverse('rates-list')
        client = APIClient()
        response = client.post(url, data=test_data, format='json', **self.headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        test_data = {'provider_uuids': [],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        # create a rate
        url = reverse('rates-list')
        response = client.post(url, data=test_data, format='json', **self.headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        rate_2_uuid = response.data.get('uuid')

        # Update rate_2_uuid rate (no provider) with the provider that is associated with rate_1
        url = reverse('rates-detail', kwargs={'uuid': rate_2_uuid})
        test_data = {'provider_uuids': [self.provider.uuid],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Create another rate of a different type that's associated with the same provider
        test_data = {'provider_uuids': [self.provider.uuid],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_REQUEST_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        # create a rate
        url = reverse('rates-list')
        client = APIClient()
        response = client.post(url, data=test_data, format='json', **self.headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        rate_3_uuid = response.data.get('uuid')

        # Attempt to update this new rate to be the same type as the other rate with provider association
        test_data = {'provider_uuids': [self.provider.uuid],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        url = reverse('rates-detail', kwargs={'uuid': rate_3_uuid})
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Attempt to update again but now remove the provider and it should be successful
        test_data = {'provider_uuids': [],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        url = reverse('rates-detail', kwargs={'uuid': rate_3_uuid})
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_patch_failure(self):
        """Test that PATCH throws exception."""
        test_data = self.fake_data
        test_data['tiered_rate'][0]['value'] = round(Decimal(random.random()), 6)
        with tenant_context(self.tenant):
            rate = Rate.objects.first()
            url = reverse('rates-detail', kwargs={'uuid': rate.uuid})
            client = APIClient()

            response = client.patch(url, test_data, format='json', **self.headers)
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_update_rate_invalid(self):
        """Test that updating an invalid rate returns an error."""
        test_data = self.fake_data
        test_data['tiered_rate'][0]['value'] = round(Decimal(random.random()), 6)

        url = reverse('rates-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_rate_success(self):
        """Test that we can delete an existing rate."""
        rate = Rate.objects.first()
        url = reverse('rates-detail', kwargs={'uuid': rate.uuid})
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # verify the rate no longer exists
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_rate_invalid(self):
        """Test that deleting an invalid rate returns an error."""
        url = reverse('rates-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_rate_list_success(self):
        """Test that we can read a list of rates."""
        url = reverse('rates-list')
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ['meta', 'links', 'data']:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get('data'), list)
        self.assertEqual(len(response.data.get('data')), 1)

        rate = response.data.get('data')[0]
        self.assertIsNotNone(rate.get('uuid'))
        self.assertIsNotNone(rate.get('uuid'))
        self.assertIsNotNone(rate.get('provider_uuids'))
        self.assertEqual(self.fake_data['metric']['name'], rate.get('metric').get('name'))

    def test_read_rate_list_success_provider_query(self):
        """Test that we can read a list of rates for a specific provider uuid."""
        url = '{}?provider_uuid={}'.format(reverse('rates-list'), self.provider.uuid)
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ['meta', 'links', 'data']:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get('data'), list)
        self.assertEqual(len(response.data.get('data')), 1)

        rate = response.data.get('data')[0]
        self.assertIsNotNone(rate.get('uuid'))
        self.assertIsNotNone(rate.get('uuid'))
        self.assertIsNotNone(rate.get('provider_uuids'))
        self.assertEqual(self.fake_data['metric']['name'], rate.get('metric').get('name'))

    def test_read_rate_list_failure_provider_query(self):
        """Test that we throw proper error for invalid provider_uuid query."""
        url = '{}?provider_uuid={}'.format(reverse('rates-list'), 'not_a_uuid')

        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIsNotNone(response.data.get('errors'))

    def test_list_rates_rbac_access(self):
        """Test GET /rates with an rbac user."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(customer, user_data, create_customer=True,
                                                       is_admin=False)

        self.initialize_request(context={'request_context': request_context, 'user_data': user_data})

        test_matrix = [{'access': {'rate': {'read': [], 'write': []}},
                        'expected_response': status.HTTP_403_FORBIDDEN},
                       {'access': {'rate': {'read': ['*'], 'write': []}},
                        'expected_response': status.HTTP_200_OK},
                       {'access': {'rate': {'read': ['not-a-uuid'], 'write': []}},
                        'expected_response': status.HTTP_500_INTERNAL_SERVER_ERROR}]
        client = APIClient()

        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                url = reverse('rates-list')
                caches['rbac'].clear()
                response = client.get(url, **request_context['request'].META)
                self.assertEqual(response.status_code, test_case.get('expected_response'))

    def test_get_rate_rbac_access(self):
        """Test GET /rates/{uuid} with an rbac user."""
        test_data = {'provider_uuids': [self.provider.uuid],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        # create a rate
        user_data = self._create_user_data()
        customer = self._create_customer_data()

        admin_request_context = self._create_request_context(customer, user_data, create_customer=True,
                                                             is_admin=True)

        url = reverse('rates-list')
        client = APIClient()
        response = client.post(url, data=test_data, format='json', **admin_request_context['request'].META)
        rate_uuid = response.data.get('uuid')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user_data = self._create_user_data()

        request_context = self._create_request_context(customer, user_data, create_customer=False,
                                                       is_admin=False)

        self.initialize_request(context={'request_context': request_context, 'user_data': user_data})

        test_matrix = [{'access': {'rate': {'read': [], 'write': []}},
                        'expected_response': status.HTTP_403_FORBIDDEN},
                       {'access': {'rate': {'read': ['*'], 'write': []}},
                        'expected_response': status.HTTP_200_OK},
                       {'access': {'rate': {'read': [str(rate_uuid)], 'write': []}},
                        'expected_response': status.HTTP_200_OK}]
        client = APIClient()

        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                url = reverse('rates-detail', kwargs={'uuid': rate_uuid})
                caches['rbac'].clear()
                response = client.get(url, **request_context['request'].META)
                self.assertEqual(response.status_code, test_case.get('expected_response'))

    def test_write_rate_rbac_access(self):
        """Test POST, PUT, and DELETE for rates with an rbac user."""
        test_data = {'provider_uuids': [self.provider.uuid],
                     'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                     'tiered_rate': [{
                         'value': round(Decimal(random.random()), 6),
                         'unit': 'USD',
                         'usage': {'usage_start': None, 'usage_end': None}
                     }]
                     }

        # create a rate as admin
        user_data = self._create_user_data()
        customer = self._create_customer_data()

        admin_request_context = self._create_request_context(customer, user_data, create_customer=True,
                                                             is_admin=True)
        with patch.object(RbacService, 'get_access_for_user', return_value=None):
            url = reverse('rates-list')
            client = APIClient()

            response = client.post(url, data=test_data, format='json', **admin_request_context['request'].META)
            rate_uuid = response.data.get('uuid')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user_data = self._create_user_data()

        request_context = self._create_request_context(customer, user_data, create_customer=False,
                                                       is_admin=False)

        self.initialize_request(context={'request_context': request_context, 'user_data': user_data})

        # POST tests
        test_matrix = [{'access': {'rate': {'read': [], 'write': []}},
                        'expected_response': status.HTTP_403_FORBIDDEN,
                        'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR}},
                       {'access': {'rate': {'read': ['*'], 'write': ['*']}},
                        'expected_response': status.HTTP_201_CREATED,
                        'metric': {'name': CostModelMetricsMap.OCP_METRIC_CPU_CORE_REQUEST_HOUR}},
                       {'access': {'rate': {'read': ['*'], 'write': ['*']}},
                        'expected_response': status.HTTP_201_CREATED,
                        'metric': {'name': CostModelMetricsMap.OCP_METRIC_MEM_GB_REQUEST_HOUR}}]
        client = APIClient()
        other_rates = []

        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                url = reverse('rates-list')
                rate_data = copy.deepcopy(test_data)
                rate_data['metric'] = test_case.get('metric')
                caches['rbac'].clear()
                response = client.post(url, data=rate_data, format='json', **request_context['request'].META)

                self.assertEqual(response.status_code, test_case.get('expected_response'))
                if response.data.get('uuid'):
                    other_rates.append(response.data.get('uuid'))

        # PUT tests
        test_matrix = [{'access': {'rate': {'read': [], 'write': []}},
                        'expected_response': status.HTTP_403_FORBIDDEN},
                       {'access': {'rate': {'read': ['*'], 'write': [str(other_rates[0])]}},
                        'expected_response': status.HTTP_403_FORBIDDEN},
                       {'access': {'rate': {'read': ['*'], 'write': ['*']}},
                        'expected_response': status.HTTP_200_OK,
                        'value': round(Decimal(random.random()), 6)},
                       {'access': {'rate': {'read': ['*'], 'write': [str(rate_uuid)]}},
                        'expected_response': status.HTTP_200_OK,
                        'value': round(Decimal(random.random()), 6)}]
        client = APIClient()

        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                url = reverse('rates-list')
                rate_data = copy.deepcopy(test_data)
                rate_data.get('tiered_rate')[0]['value'] = test_case.get('value')

                url = reverse('rates-detail', kwargs={'uuid': rate_uuid})
                caches['rbac'].clear()
                response = client.put(url, data=rate_data, format='json', **request_context['request'].META)

                self.assertEqual(response.status_code, test_case.get('expected_response'))

        # DELETE tests
        test_matrix = [{'access': {'rate': {'read': [], 'write': []}},
                        'expected_response': status.HTTP_403_FORBIDDEN,
                        'rate_uuid': rate_uuid},
                       {'access': {'rate': {'read': ['*'], 'write': [str(other_rates[0])]}},
                        'expected_response': status.HTTP_403_FORBIDDEN,
                        'rate_uuid': rate_uuid},
                       {'access': {'rate': {'read': ['*'], 'write': ['*']}},
                        'expected_response': status.HTTP_204_NO_CONTENT,
                        'rate_uuid': rate_uuid},
                       {'access': {'rate': {'read': ['*'], 'write': [str(other_rates[0])]}},
                        'expected_response': status.HTTP_204_NO_CONTENT,
                        'rate_uuid': other_rates[0]}]
        client = APIClient()
        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                test_data.get('tiered_rate')[0]['value'] = test_case.get('value')
                url = reverse('rates-detail', kwargs={'uuid': test_case.get('rate_uuid')})
                caches['rbac'].clear()
                response = client.delete(url, **request_context['request'].META)
                self.assertEqual(response.status_code, test_case.get('expected_response'))
