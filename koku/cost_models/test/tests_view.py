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
"""Test the Cost Model views."""
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
from cost_models.models import CostModel, CostModelMap
from cost_models.serializers import CostModelSerializer
from koku.rbac import RbacService


class CostModelViewTests(IamTestCase):
    """Test the Cost Model view."""

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

        self.ocp_metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        self.ocp_source_type = 'OCP'
        tiered_rates = [
            {
                'value': round(Decimal(random.random()), 6),
                'unit': 'USD',
                'usage': {'usage_start': None, 'usage_end': None}
            }
        ]
        self.fake_data = {
            'name': 'Test Cost Model',
            'description': 'Test',
            'source_type': self.ocp_source_type,
            'provider_uuids': [self.provider.uuid],
            'rates': [
                {
                    'metric': {'name': self.ocp_metric},
                    'tiered_rates': tiered_rates
                }
            ]
        }

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.fake_data,
                                             context=request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches['rbac'].clear()
        self.initialize_request()

    def tearDown(self):
        """Tear down rate view tests."""
        with tenant_context(self.tenant):
            CostModel.objects.all().delete()
            CostModelMap.objects.all().delete()
            Provider.objects.all().delete()
            User.objects.all().delete()

    def test_create_cost_model_success(self):
        """Test that we can create a cost model."""
        # create a cost model
        url = reverse('costmodels-list')
        client = APIClient()
        response = client.post(url, data=self.fake_data,
                               format='json', **self.headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # test that we can retrieve the cost model
        url = reverse('costmodels-detail', kwargs={'uuid': response.data.get('uuid')})
        response = client.get(url, **self.headers)
        self.assertIsNotNone(response.data.get('uuid'))
        self.assertIsNotNone(response.data.get('providers'))
        for rate in response.data.get('rates', []):
            self.assertEqual(self.fake_data['rates'][0]['metric']['name'],
                             rate.get('metric', {}).get('name'))
            self.assertIsNotNone(rate.get('tiered_rates'))

    def test_create_new_cost_model_map_association_for_provider(self):
        """Test that the CostModelMap updates for a new cost model."""
        url = reverse('costmodels-list')
        client = APIClient()

        with tenant_context(self.tenant):
            original_cost_model = CostModel.objects.all()[0]
        response = client.post(url, data=self.fake_data,
                               format='json', **self.headers)
        new_cost_model_uuid = response.data.get('uuid')

        # Test that the previous cost model for this provider is no longer
        # associated
        with tenant_context(self.tenant):
            result = CostModelMap.objects.filter(
                cost_model_id=original_cost_model.uuid
            ).all()
            self.assertEqual(len(result), 0)
            # Test that the new cost model is associated to the provider
            result = CostModelMap.objects.filter(
                cost_model_id=new_cost_model_uuid
            ).all()
            self.assertEqual(len(result), 1)

    def test_create_cost_model_invalid_rates(self):
        """Test that creating a cost model with invalid rates returns an error."""
        url = reverse('costmodels-list')
        client = APIClient()

        test_data = copy.deepcopy(self.fake_data)
        test_data['rates'][0]['metric']['name'] = self.fake.word()
        response = client.post(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_cost_model_invalid_source_type(self):
        """Test that an invalid source type is not allowed."""
        url = reverse('costmodels-list')
        client = APIClient()

        test_data = copy.deepcopy(self.fake_data)
        test_data['source_type'] = 'Bad Source'
        response = client.post(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_cost_model_success(self):
        """Test that we can read a cost model."""
        cost_model = CostModel.objects.first()
        url = reverse('costmodels-detail', kwargs={'uuid': cost_model.uuid})
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get('uuid'))
        self.assertIsNotNone(response.data.get('providers'))
        for rate in response.data.get('rates', []):
            self.assertEqual(self.ocp_metric,
                             rate.get('metric', {}).get('name'))
            self.assertIsNotNone(rate.get('tiered_rates'))

    def test_filter_cost_model(self):
        """Test that we can filter a cost model."""
        client = APIClient()
        url = '%s?name=Cost,Production' % reverse('costmodels-list')
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get('data')
        self.assertEqual(len(results), 0)

        url = '%s?name=Cost,Test&source_type=AWS' % reverse('costmodels-list')
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get('data')
        self.assertEqual(len(results), 0)

        url = '%s?name=Cost,Test' % reverse('costmodels-list')
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get('data')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Test Cost Model')

    def test_read_cost_model_invalid(self):
        """Test that reading an invalid cost_model returns an error."""
        url = reverse('costmodels-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_cost_model_success(self):
        """Test that we can update an existing rate."""
        new_value = round(Decimal(random.random()), 6)
        self.fake_data['rates'][0]['tiered_rates'][0]['value'] = new_value

        cost_model = CostModel.objects.first()
        url = reverse('costmodels-detail', kwargs={'uuid': cost_model.uuid})
        client = APIClient()
        response = client.put(url, self.fake_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIsNotNone(response.data.get('uuid'))
        rates = response.data.get('rates', [])
        self.assertEqual(rates[0].get('tiered_rates', [])[0].get('value'),
                         new_value)
        self.assertEqual(rates[0].get('metric', {}).get('name'), self.ocp_metric)

    def test_update_cost_model_failure(self):
        """Test that we update fails with metric type duplication."""
        # create a cost model
        url = reverse('costmodels-list')
        client = APIClient()
        response = client.post(url, data=self.fake_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Add another entry with tiered rates for this metric
        rates = self.fake_data['rates']
        rates.append(rates[0])

        # Make sure the update with duplicate rate information fails
        url = reverse('costmodels-detail', kwargs={'uuid': response.data.get('uuid')})
        response = client.put(url, self.fake_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_failure(self):
        """Test that PATCH throws exception."""
        test_data = self.fake_data
        test_data['rates'][0]['tiered_rates'][0]['value'] = round(Decimal(random.random()), 6)
        with tenant_context(self.tenant):
            cost_model = CostModel.objects.first()
            url = reverse('costmodels-detail', kwargs={'uuid': cost_model.uuid})
            client = APIClient()

            response = client.patch(url, test_data, format='json', **self.headers)
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_update_cost_model_invalid(self):
        """Test that updating an invalid cost model returns an error."""
        test_data = self.fake_data
        test_data['rates'][0]['tiered_rates'][0]['value'] = round(Decimal(random.random()), 6)

        url = reverse('costmodels-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.put(url, test_data, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_cost_model_success(self):
        """Test that we can delete an existing rate."""
        cost_model = CostModel.objects.first()
        url = reverse('costmodels-detail', kwargs={'uuid': cost_model.uuid})
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # verify the cost model no longer exists
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_cost_model_invalid(self):
        """Test that deleting an invalid cost model returns an error."""
        url = reverse('costmodels-detail', kwargs={'uuid': uuid4()})
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_cost_model_list_success(self):
        """Test that we can read a list of cost models."""
        url = reverse('costmodels-list')
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ['meta', 'links', 'data']:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get('data'), list)
        self.assertEqual(len(response.data.get('data')), 1)

        cost_model = response.data.get('data')[0]
        self.assertIsNotNone(cost_model.get('uuid'))
        self.assertIsNotNone(cost_model.get('providers'))
        self.assertEqual(self.fake_data['rates'][0]['metric']['name'],
                         cost_model.get('rates', [])[0].get('metric', {}).get('name'))
        self.assertEqual(self.fake_data['rates'][0]['tiered_rates'][0].get('value'),
                         str(cost_model.get('rates', [])[0].get('tiered_rates', [])[0].get('value')))

    def test_read_cost_model_list_success_provider_query(self):
        """Test that we can read a list of cost models for a specific provider."""
        url = '{}?provider_uuid={}'.format(reverse('costmodels-list'), self.provider.uuid)
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ['meta', 'links', 'data']:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get('data'), list)
        self.assertEqual(len(response.data.get('data')), 1)

        cost_model = response.data.get('data')[0]
        self.assertIsNotNone(cost_model.get('uuid'))
        self.assertIsNotNone(cost_model.get('providers'))
        self.assertEqual(self.fake_data['rates'][0]['metric']['name'],
                         cost_model.get('rates', [])[0].get('metric', {}).get('name'))
        self.assertEqual(self.fake_data['rates'][0]['tiered_rates'][0].get('value'),
                         str(cost_model.get('rates', [])[0].get('tiered_rates', [])[0].get('value')))

    def test_read_cost_model_list_failure_provider_query(self):
        """Test that we throw proper error for invalid provider_uuid query."""
        url = '{}?provider_uuid={}'.format(reverse('costmodels-list'), 'not_a_uuid')

        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data.get('errors'))

    def test_return_error_on_invalid_query_field(self):
        """Test that an error is thrown when a query field is incorrect."""
        url = '{}?wrong={}'.format(reverse('costmodels-list'), 'query')

        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_cost_model_rate_rbac_access(self):
        """Test GET /costmodels with an rbac user."""
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
                url = reverse('costmodels-list')
                caches['rbac'].clear()
                response = client.get(url, **request_context['request'].META)
                self.assertEqual(response.status_code, test_case.get('expected_response'))

    def test_get_cost_model_rate_rbac_access(self):
        """Test GET /costmodels/{uuid} with an rbac user."""
        # create a cost model
        user_data = self._create_user_data()
        customer = self._create_customer_data()

        admin_request_context = self._create_request_context(customer, user_data, create_customer=True,
                                                             is_admin=True)

        url = reverse('costmodels-list')
        client = APIClient()
        response = client.post(url, data=self.fake_data, format='json', **admin_request_context['request'].META)
        cost_model_uuid = response.data.get('uuid')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user_data = self._create_user_data()

        request_context = self._create_request_context(customer, user_data, create_customer=False,
                                                       is_admin=False)

        self.initialize_request(context={'request_context': request_context, 'user_data': user_data})

        test_matrix = [{'access': {'rate': {'read': [], 'write': []}},
                        'expected_response': status.HTTP_403_FORBIDDEN},
                       {'access': {'rate': {'read': ['*'], 'write': []}},
                        'expected_response': status.HTTP_200_OK},
                       {'access': {'rate': {'read': [str(cost_model_uuid)], 'write': []}},
                        'expected_response': status.HTTP_200_OK}]
        client = APIClient()

        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                url = reverse('costmodels-detail', kwargs={'uuid': cost_model_uuid})
                caches['rbac'].clear()
                response = client.get(url, **request_context['request'].META)
                self.assertEqual(response.status_code, test_case.get('expected_response'))

    def test_write_cost_model_rate_rbac_access(self):
        """Test POST, PUT, and DELETE for rates with an rbac user."""
        # create a rate as admin
        user_data = self._create_user_data()
        customer = self._create_customer_data()

        admin_request_context = self._create_request_context(customer, user_data, create_customer=True,
                                                             is_admin=True)
        with patch.object(RbacService, 'get_access_for_user', return_value=None):
            url = reverse('costmodels-list')
            client = APIClient()

            response = client.post(url, data=self.fake_data, format='json', **admin_request_context['request'].META)
            cost_model_uuid = response.data.get('uuid')
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
        other_cost_models = []

        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                url = reverse('costmodels-list')
                rate_data = copy.deepcopy(self.fake_data)
                rate_data['rates'][0]['metric'] = test_case.get('metric')
                caches['rbac'].clear()
                response = client.post(url, data=rate_data, format='json', **request_context['request'].META)

                self.assertEqual(response.status_code, test_case.get('expected_response'))
                if response.data.get('uuid'):
                    other_cost_models.append(response.data.get('uuid'))

        # PUT tests
        test_matrix = [{'access': {'rate': {'read': [], 'write': []}},
                        'expected_response': status.HTTP_403_FORBIDDEN},
                       {'access': {'rate': {'read': ['*'], 'write': [str(other_cost_models[0])]}},
                        'expected_response': status.HTTP_403_FORBIDDEN},
                       {'access': {'rate': {'read': ['*'], 'write': ['*']}},
                        'expected_response': status.HTTP_200_OK,
                        'value': round(Decimal(random.random()), 6)},
                       {'access': {'rate': {'read': ['*'], 'write': [str(cost_model_uuid)]}},
                        'expected_response': status.HTTP_200_OK,
                        'value': round(Decimal(random.random()), 6)}]
        client = APIClient()

        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                url = reverse('costmodels-list')
                rate_data = copy.deepcopy(self.fake_data)
                rate_data['rates'][0].get('tiered_rates')[0]['value'] = test_case.get('value')

                url = reverse('costmodels-detail', kwargs={'uuid': cost_model_uuid})
                caches['rbac'].clear()
                response = client.put(url, data=rate_data, format='json', **request_context['request'].META)

                self.assertEqual(response.status_code, test_case.get('expected_response'))

        # DELETE tests
        test_matrix = [{'access': {'rate': {'read': [], 'write': []}},
                        'expected_response': status.HTTP_403_FORBIDDEN,
                        'cost_model_uuid': cost_model_uuid},
                       {'access': {'rate': {'read': ['*'], 'write': [str(other_cost_models[0])]}},
                        'expected_response': status.HTTP_403_FORBIDDEN,
                        'cost_model_uuid': cost_model_uuid},
                       {'access': {'rate': {'read': ['*'], 'write': ['*']}},
                        'expected_response': status.HTTP_204_NO_CONTENT,
                        'cost_model_uuid': cost_model_uuid},
                       {'access': {'rate': {'read': ['*'], 'write': [str(other_cost_models[0])]}},
                        'expected_response': status.HTTP_204_NO_CONTENT,
                        'cost_model_uuid': other_cost_models[0]}]
        client = APIClient()
        for test_case in test_matrix:
            with patch.object(RbacService, 'get_access_for_user', return_value=test_case.get('access')):
                url = reverse('costmodels-detail', kwargs={'uuid': test_case.get('cost_model_uuid')})
                caches['rbac'].clear()
                response = client.delete(url, **request_context['request'].META)
                self.assertEqual(response.status_code, test_case.get('expected_response'))
