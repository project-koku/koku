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
from unittest.mock import patch

from django.urls import reverse
from providers.provider_access import ProviderAccessor
from rest_framework.test import APIClient

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.models import Customer, User
from api.provider.models import Provider
from api.provider.provider_manager import ProviderManager


class ProviderViewTest(IamTestCase):
    """Tests the provider view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.user_data = self._create_user_data()
        self.customer = self._create_customer_data()
        self.request_context = self._create_request_context(self.customer,
                                                            self.user_data)
        self.headers = self.request_context['request'].META
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

    def tearDown(self):
        """Tear down user tests."""
        super().tearDown()
        Customer.objects.all().delete()
        User.objects.all().delete()

    def create_provider(self, bucket_name, iam_arn, headers=None):
        """Create a provider and return response."""
        req_headers = self.headers
        if headers:
            req_headers = headers
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
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

    def test_create_provider(self):
        """Test create a provider."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, 201)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

    def test_create_provider_no_duplicate(self):
        """Test create a provider should catch duplicate PRN."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, 201)
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, 400)

    def test_list_provider(self):
        """Test list providers."""
        iam_arn1 = 'arn:aws:s3:::my_s3_bucket'
        bucket_name1 = 'my_s3_bucket'
        iam_arn2 = 'arn:aws:s3:::a_s3_bucket'
        bucket_name2 = 'a_s3_bucket'
        self.create_provider(bucket_name1, iam_arn1)
        request_context = self._create_request_context(self._create_customer_data(),
                                                       self._create_user_data())
        headers = request_context['request'].META
        self.create_provider(bucket_name2, iam_arn2, headers)
        url = reverse('provider-list')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        results = json_result.get('results')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)

    def test_get_provider(self):
        """Test get a provider."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn, )
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        uuid = json_result.get('uuid')
        self.assertIsNotNone(uuid)
        self.assertEqual(uuid, provider_uuid)

    def test_get_provider_other_customer(self):
        """Test get a provider for another customer should fail."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        create_response = self.create_provider(bucket_name, iam_arn)
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        url = reverse('provider-detail', args=[provider_uuid])
        request_context = self._create_request_context(self._create_customer_data(),
                                                       self._create_user_data())
        headers = request_context['request'].META
        client = APIClient()
        response = client.get(url, **headers)
        self.assertEqual(response.status_code, 404)

    def test_remove_provider_with_regular_user(self):
        """Test removing a provider with the user account that created it."""
        # Create a Provider as a regular user
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, 201)

        # Verify that the Provider creation was successful
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data['username'])

        # Remove Provider as the regular user that created the Provider
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, 204)

    def test_remove_provider_with_remove_exception(self):
        """Test removing a provider with a database error."""
        # Create Provider with customer owner token
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn)
        self.assertEqual(response.status_code, 201)

        # Verify that the Provider creation was successful
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('account_id'),
                         self.customer.get('account_id'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.user_data.get('username'))

        # Remove Provider with customer token
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        with patch.object(ProviderManager, 'remove', side_effect=Exception):
            response = client.delete(url, **self.headers)
            self.assertEqual(response.status_code, 500)
