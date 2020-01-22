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
"""Test the Provider views."""
import copy
from unittest.mock import patch
from uuid import UUID, uuid4

import faker
from django.db.utils import InterfaceError
from django.urls import reverse
from rest_framework import serializers
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.provider_manager import ProviderManager, ProviderManagerError
from api.provider.test import PROVIDERS, create_generic_provider
from providers.provider_access import ProviderAccessor

fields = ['name', 'type', 'authentication', 'billing_source']
FAKE = faker.Faker()


class ProviderViewTest(IamTestCase):
    """Tests the provider view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        # serializer = UserSerializer(data=self.user_data, context=self.request_context)
        # if serializer.is_valid(raise_exception=True):
        #     serializer.save()

    def create_provider(self, bucket_name, iam_arn,
                        headers=None, provider_type=Provider.PROVIDER_AWS):
        """Create a provider and return response."""
        req_headers = self.headers
        if headers:
            req_headers = headers
        provider = {'name': 'test_provider',
                    'type': provider_type,
                    'authentication': {
                        'provider_resource_name': iam_arn
                    },
                    'billing_source': {
                        'bucket': bucket_name
                    }}
        url = reverse('provider-list')
        with patch.object(ProviderAccessor, 'cost_usage_source_ready', returns=True):
            client = APIClient()
            return client.post(url, data=provider, format='json', **req_headers)

    def create_cost_model(self, provider_uuids, headers=None):
        """Create a cost model and return response."""
        req_headers = self.headers
        if headers:
            req_headers = headers
        cost_model_data = {
            'name': FAKE.catch_phrase(),
            'source_type': Provider.PROVIDER_AWS,
            'description': FAKE.paragraph(),
            'rates': [],
            'markup': {
                'value': FAKE.pyint() % 100, 'unit': 'percent'
            },
            'provider_uuids': [UUID(p) for p in provider_uuids]
        }
        url = reverse('costmodels-list')
        with patch.object(ProviderAccessor, 'cost_usage_source_ready', returns=True):
            client = APIClient()
            result = client.post(url, data=cost_model_data, format='json', **req_headers)
        return result

    def test_create_aws_with_no_provider_resource_name(self):
        """Test missing provider_resource_name returns 400."""
        req_headers = self.headers
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
                    'authentication': {
                        'provider_resource_name': ''
                    },
                    'billing_source': {
                        'bucket': ''
                    }}
        url = reverse('provider-list')
        client = APIClient()
        response = client.post(url, data=provider, format='json', **req_headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_aws_type_camel_casing(self):
        """Test creating a provider with type camel cased."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn, provider_type='aWs')
        json_result = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(json_result.get('type'), Provider.PROVIDER_AWS)

    @patch('providers.aws.provider._get_sts_access', return_value={'empty': 'dict'})
    def test_create_aws_with_no_bucket_name(self, mock_sts_return):
        """Test missing bucket returns 400."""
        req_headers = self.headers
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
                    'authentication': {
                        'provider_resource_name': 'arn:aws:s3:::my_s3_bucket'
                    },
                    'billing_source': {
                        'bucket': ''
                    }}
        url = reverse('provider-list')
        client = APIClient()
        response = client.post(url, data=provider, format='json', **req_headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_provider(self):
        """Test create a provider."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer_data.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

    def test_create_provider_shared_arn(self):
        """Test that a provider can reuse an arn."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer_data.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_different_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer_data.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

    def test_create_provider_shared_bucket(self):
        """Test that a provider can reuse a bucket."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer_data.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

        iam_arn = 'arn:aws:s3:::my_s3_bucket_different'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer_data.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

    def test_create_provider_shared_arn_bucket_fails(self):
        """Test that a provider can not reuse bucket AND arn."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer_data.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_provider(self):
        """
        Test list providers.

        This test asserts a combination of factors. We create two providers,
        but each provider belongs to a different user. The first provider has
        a cost model, but the second does not. We assert that each provider is
        listed only for its respective user's request context.
        """
        # Define the context for the second user; this must happen FIRST for reasons
        # currently unknown. If you call this after creating the first provider, DB
        # exceptions are raised (django.db.utils.OperationalError: cannot ALTER TABLE)
        request_context = self._create_request_context(
            self.create_mock_customer_data(),
            self._create_user_data(),
            create_tenant=True)
        alternate_headers = request_context['request'].META

        # Create a provider with a cost model.
        iam_arn1 = 'arn:aws:s3:::my_s3_bucket'
        bucket_name1 = 'my_s3_bucket'
        first_create_response = self.create_provider(bucket_name1, iam_arn1)
        first_provider_result = first_create_response.json()
        first_provider_uuid = first_provider_result.get('uuid')
        create_cost_model_response = self.create_cost_model([first_provider_uuid])
        cost_model_result = create_cost_model_response.json()
        self.assertIsNotNone(cost_model_result['uuid'])
        self.assertIsNotNone(cost_model_result['name'])
        expected_cost_model_info = {
            'name': cost_model_result['name'], 'uuid': cost_model_result['uuid']
        }

        # Create a second provider but for a different user.
        iam_arn2 = 'arn:aws:s3:::a_s3_bucket'
        bucket_name2 = 'a_s3_bucket'
        second_create_response = self.create_provider(
            bucket_name2, iam_arn2, alternate_headers
        )
        second_provider_result = second_create_response.json()
        second_provider_uuid = second_provider_result.get('uuid')

        # List and expect it to contain only the first provider with cost model.
        url = reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get('data')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['uuid'], first_provider_uuid)
        self.assertEqual(results[0].get('infrastructure'), 'Unknown')
        self.assertEqual(results[0].get('stats'), None)
        self.assertEqual(len(results[0]['cost_models']), 1)
        self.assertEqual(results[0]['cost_models'][0], expected_cost_model_info)

        # List as the different user and expect the second provider with no cost model.
        response = client.get(url, **alternate_headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get('data')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['uuid'], second_provider_uuid)
        self.assertEqual(len(results[0]['cost_models']), 0)

    @patch('api.provider.view.ProviderViewSet.list')
    def test_list_provider_exception_return_424(self, mocked_list):
        """Test that 424 is returned when view raises InterfaceError."""
        mocked_list.side_effect = InterfaceError('connection already closed')
        url = reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_424_FAILED_DEPENDENCY)

    def test_get_provider(self):
        """Test get a provider."""
        # Set up all the data for this test.
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn, )
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        create_cost_model_response = self.create_cost_model([provider_uuid])
        cost_model_result = create_cost_model_response.json()
        self.assertIsNotNone(cost_model_result['uuid'])
        self.assertIsNotNone(cost_model_result['name'])
        expected_cost_model_info = {
            'name': cost_model_result['name'], 'uuid': cost_model_result['uuid']
        }

        # Call the API for testing the results.
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        uuid = json_result.get('uuid')
        self.assertIsNotNone(uuid)
        self.assertEqual(uuid, provider_uuid)
        self.assertEqual(json_result.get('stats'), None)
        self.assertEqual(json_result.get('infrastructure'), 'Unknown')
        cost_models = json_result.get('cost_models')
        self.assertEqual(len(cost_models), 1)
        self.assertEqual(cost_models[0], expected_cost_model_info)

    def test_filter_providers_by_name_contains(self):
        """Test that providers that contain name appear."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn, )
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        url = '%s?mame=provider' % reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get('data')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)

    def test_filter_providers_by_name_not_contain(self):
        """Test that all providers that do not contain name will not appear."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn, )
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        url = '%s?name=blabla' % reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get('data')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 0)

    def test_get_provider_other_customer(self):
        """Test get a provider for another customer should fail."""
        request_context = self._create_request_context(self.create_mock_customer_data(),
                                                       self._create_user_data(),
                                                       create_tenant=True)
        headers = request_context['request'].META
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn)
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        response = client.get(url, **headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_provider_with_regular_user(self):
        """Test removing a provider with the user account that created it."""
        # Create a Provider as a regular user
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify that the Provider creation was successful
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer_data.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data['username'])

        # Remove Provider as the regular user that created the Provider
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_remove_provider_with_remove_exception(self):
        """Test removing a provider with a database error."""
        # Create Provider with customer owner token
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify that the Provider creation was successful
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer_data.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

        # Remove Provider with customer token
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        with patch.object(ProviderManager, 'remove', side_effect=Exception):
            response = client.delete(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_remove_invalid_provider(self):
        """Test removing an invalid provider with the user."""
        # Create a Provider
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Remove invalid Provider as the regular user
        url = reverse('provider-detail', args=[uuid4()])
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_invalid_provider_non_uuid(self):
        """Test removing an invalid provider with the non_uuid."""
        # Create a Provider
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Remove invalid Provider as the regular user
        url = reverse('provider-detail', args=['23333223223'])
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_for_ocp_provider(self):
        """Test PUT update for OCP provider."""
        response, provider = create_generic_provider(Provider.PROVIDER_OCP, self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()

        name = 'new_name'
        auth = {'provider_resource_name': 'testing_123'}
        provider = copy.deepcopy(PROVIDERS[Provider.PROVIDER_OCP])
        provider['name'] = name
        provider['authentication'] = auth

        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        put_response = client.put(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_200_OK)

        put_json_result = put_response.json()
        self.assertEqual(put_json_result.get('name'), name)
        self.assertEqual(put_json_result.get('authentication').get('credentials'), auth)

    def test_create_ocp_type_camel_casing(self):
        """Test creating a provider with type camel cased."""
        response, _ = create_generic_provider('oCp', self.headers)
        json_result = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(json_result.get('type'), Provider.PROVIDER_OCP)

    def test_create_aws_type_lower_case(self):
        """Test creating a provider with type camel cased."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn, provider_type='aws')
        json_result = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(json_result.get('type'), Provider.PROVIDER_AWS)

    @patch.object(ProviderAccessor, 'cost_usage_source_ready', returns=True)
    def test_put_for_aws_provider(self, mock_access):
        """Test PUT update for AWS provider."""
        response, provider = create_generic_provider(Provider.PROVIDER_AWS, self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()

        name = 'new_name'
        provider = copy.deepcopy(PROVIDERS[Provider.PROVIDER_AWS])
        provider['name'] = name

        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        put_response = client.put(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_200_OK)

        put_json_result = put_response.json()
        self.assertEqual(put_json_result.get('name'), name)

    def test_put_for_aws_provider_error(self):
        """Test PUT update for AWS provider with error."""
        with patch.object(ProviderAccessor, 'cost_usage_source_ready', returns=True):
            response, provider = create_generic_provider(Provider.PROVIDER_AWS, self.headers)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        with patch.object(ProviderAccessor, 'cost_usage_source_ready',
                          side_effect=serializers.ValidationError):
            json_result = response.json()
            name = 'new_name'
            provider = copy.deepcopy(PROVIDERS[Provider.PROVIDER_AWS])
            provider['name'] = name

            url = reverse('provider-detail', args=[json_result.get('uuid')])
            client = APIClient()
            put_response = client.put(url, data=provider, format='json', **self.headers)
            self.assertEqual(put_response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(Provider.objects.get(uuid=json_result.get('uuid')).active)

    @patch.object(ProviderAccessor, 'cost_usage_source_ready', returns=True)
    def test_put_for_azure_provider(self, mock_access):
        """Test PUT update for AZURE provider."""
        response, provider = create_generic_provider(Provider.PROVIDER_AZURE, self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()

        name = 'new_name'
        provider = copy.deepcopy(PROVIDERS[Provider.PROVIDER_AZURE])
        provider['name'] = name

        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        put_response = client.put(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_200_OK)

        put_json_result = put_response.json()
        self.assertEqual(put_json_result.get('name'), name)

    def test_create_azure_type_camel_casing(self):
        """Test creating a provider with type camel cased."""
        response, _ = create_generic_provider('AzUrE', self.headers)
        json_result = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(json_result.get('type'), Provider.PROVIDER_AZURE)

    @patch.object(ProviderAccessor, 'cost_usage_source_ready', returns=True)
    def test_put_for_provider_type_change(self, mock_access):
        """Test that provider_type change thru PUT request results in error."""
        response, provider = create_generic_provider(Provider.PROVIDER_AWS, self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()

        provider = copy.deepcopy(PROVIDERS[Provider.PROVIDER_AWS])
        provider['type'] = Provider.PROVIDER_OCP

        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        put_response = client.put(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_not_supported(self):
        """Test that PATCH request returns 405."""
        response, provider = create_generic_provider(Provider.PROVIDER_AZURE, self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()

        name = 'new_name'
        provider = copy.deepcopy(PROVIDERS[Provider.PROVIDER_AZURE])
        provider['name'] = name

        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        put_response = client.patch(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_deleted_before_put_returns_400(self):
        """Test if 400 is raised when a PUT is called on deleted provider."""
        response, provider = create_generic_provider(Provider.PROVIDER_AZURE, self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()

        name = 'new_name'
        provider = copy.deepcopy(PROVIDERS[Provider.PROVIDER_AZURE])
        provider['name'] = name

        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        put_response = client.put(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_404_NOT_FOUND)

    @patch.object(ProviderAccessor, 'cost_usage_source_ready', returns=True)
    def test_put_for_integrity_check(self, mock_access):
        """Test PUT update: Make 2 providers match should give integrity error."""
        iam_arn1 = 'arn:aws:s3:::my_s3_bucket'
        bucket_name1 = 'my_s3_bucket'
        response = self.create_provider(bucket_name1, iam_arn1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        provider = response.json()
        provider_uuid = provider.get('uuid')
        put_provider_resource_name = 'arn:aws:s3:::my_s3_bucket_PUT'
        put_bucket = 'my_s3_bucket_PUT'
        provider['authentication']['credentials']['provider_resource_name'] = put_provider_resource_name
        provider['billing_source']['data_source']['bucket'] = put_bucket
        provider['name'] = 'PUT-test'
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        put_response = client.put(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_200_OK)

        response = self.create_provider(bucket_name1, iam_arn1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        provider = response.json()
        provider_uuid = provider.get('uuid')
        put_provider_resource_name = 'arn:aws:s3:::my_s3_bucket_PUT'
        put_bucket = 'my_s3_bucket_PUT'
        provider['authentication']['credentials']['provider_resource_name'] = put_provider_resource_name
        provider['billing_source']['data_source']['bucket'] = put_bucket
        provider['name'] = 'PUT-test'
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        put_response = client.put(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch.object(ProviderAccessor, 'cost_usage_source_ready', returns=True)
    def test_put_with_existing_auth_and_bill(self, mock_access):
        """Test PUT when update matches existing authentication and billing_source."""
        iam_arn1 = 'arn:aws:s3:::my_s3_bucket'
        bucket_name1 = 'my_s3_bucket'
        response1 = self.create_provider(bucket_name1, iam_arn1)
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        response1 = self.create_provider(bucket_name1, iam_arn1)
        self.assertEqual(response1.status_code, status.HTTP_400_BAD_REQUEST)

        iam_arn2 = 'arn:aws:s3:::my_s3_bucket_two'
        bucket_name2 = 'my_s3_bucket_two'
        response2 = self.create_provider(bucket_name2, iam_arn2)
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

        provider = response2.json()
        provider_uuid = provider.get('uuid')
        provider['authentication']['credentials']['provider_resource_name'] = iam_arn1
        provider['billing_source']['data_source']['bucket'] = bucket_name1
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        put_response = client.put(url, data=provider, format='json', **self.headers)
        self.assertEqual(put_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_provider_with_update_exception(self):
        """Test updating a provider with a database error."""
        # Create Provider with customer owner token
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        json_result = response.json()

        # Update Provider with customer token
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        with patch.object(ProviderManager, 'update', side_effect=ProviderManagerError('Update Error.')):
            response = client.put(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_get_provider_with_stats(self):
        """Test get a provider with status."""
        # Set up all the data for this test.
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn, )
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)

        # Call the API for testing the results.
        url = '%s?stats=true' % reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertEqual(json_result.get('stats'), {})

        url = '%s?stats=True' % reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertEqual(json_result.get('stats'), {})

        url = '%s?stats=false' % reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertEqual(json_result.get('stats'), None)

    def test_get_provider_with_stats_invalid(self):
        """Test get a provider with bad status value."""
        # Set up all the data for this test.
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn, )
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)

        # Call the API for testing the results.
        url = '%s?stats=bla' % reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_provider_list_with_stats(self):
        """Test get provider list with status."""
        # Set up all the data for this test.
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn, )
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)

        # Call the API for testing the results.
        url = '%s?stats=true' % reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        for provider in json_result.get('data'):
            self.assertEqual(provider.get('stats'), {})

        url = '%s?stats=True' % reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        for provider in json_result.get('data'):
            self.assertEqual(provider.get('stats'), {})

        url = '%s?stats=false' % reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        for provider in json_result.get('data'):
            self.assertEqual(provider.get('stats'), None)

    def test_get_provider_list_with_stats_invalid(self):
        """Test get a provider list with bad status value."""
        # Set up all the data for this test.
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn, )
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)

        # Call the API for testing the results.
        url = '%s?stats=bla' % reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
