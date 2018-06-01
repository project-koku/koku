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
from providers.provider_access import ProviderAccess
from rest_framework.test import APIClient

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.models import Customer, User
from api.provider.models import Provider


class ProviderViewTest(IamTestCase):
    """Tests the provider view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.create_service_admin()
        for customer in self.customer_data:
            response = self.create_customer(customer)
            self.assertEqual(response.status_code, 201)

    def tearDown(self):
        """Tear down user tests."""
        super().tearDown()
        Customer.objects.all().delete()
        User.objects.all().delete()

    def create_provider(self, bucket_name, iam_arn, token):
        """Create a provider and return response."""
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
                    'authentication': {
                        'provider_resource_name': iam_arn
                    },
                    'billing_source': {
                        'bucket': bucket_name
                    }}
        url = reverse('provider-list')
        with patch.object(ProviderAccess, 'cost_usage_source_ready', returns=True):
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=token)
            return client.post(url, data=provider, format='json')

    def test_create_provider(self):
        """Test create a provider."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token = self.get_customer_owner_token(self.customer_data[0])
        response = self.create_provider(bucket_name, iam_arn, token)
        self.assertEqual(response.status_code, 201)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('name'),
                         self.customer_data[0].get('name'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.customer_data[0].get('owner').get('username'))

    def test_create_provider_no_duplicate(self):
        """Test create a provider should catch duplicate PRN."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token = self.get_customer_owner_token(self.customer_data[0])
        response = self.create_provider(bucket_name, iam_arn, token)
        self.assertEqual(response.status_code, 201)
        response = self.create_provider(bucket_name, iam_arn, token)
        self.assertEqual(response.status_code, 400)

    def test_create_provider_anon(self):
        """Test create a provider with an anonymous user."""
        url = reverse('provider-list')
        client = APIClient()
        provider = {'name': 'test_provider',
                    'type': Provider.PROVIDER_AWS,
                    'authentication': {
                        'provider_resource_name': 'arn:aws:s3:::my_s3_bucket'
                    },
                    'billing_source': {
                        'bucket': 'my_s3_bucket'
                    }}
        response = client.post(url, data=provider, format='json')
        self.assertEqual(response.status_code, 401)

    def test_list_provider(self):
        """Test list providers."""
        iam_arn1 = 'arn:aws:s3:::my_s3_bucket'
        bucket_name1 = 'my_s3_bucket'
        iam_arn2 = 'arn:aws:s3:::a_s3_bucket'
        bucket_name2 = 'a_s3_bucket'
        token1 = self.get_customer_owner_token(self.customer_data[0])
        self.create_provider(bucket_name1, iam_arn1, token1)
        token2 = self.get_customer_owner_token(self.customer_data[1])
        self.create_provider(bucket_name2, iam_arn2, token2)
        url = reverse('provider-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token1)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        results = json_result.get('results')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)

    def test_list_provider_anon(self):
        """Test list providers with an anonymous user."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token1 = self.get_customer_owner_token(self.customer_data[0])
        self.create_provider(bucket_name, iam_arn, token1)
        url = reverse('provider-list')
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_get_provider(self):
        """Test get a provider."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token1 = self.get_customer_owner_token(self.customer_data[0])
        create_response = self.create_provider(bucket_name, iam_arn, token1)
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token1)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        uuid = json_result.get('uuid')
        self.assertIsNotNone(uuid)
        self.assertEqual(uuid, provider_uuid)

    def test_get_provider_other_customer(self):
        """Test get a provider for another customer should fail."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token1 = self.get_customer_owner_token(self.customer_data[0])
        token2 = self.get_customer_owner_token(self.customer_data[1])
        create_response = self.create_provider(bucket_name, iam_arn, token1)
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token2)
        response = client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_get_provider_with_no_group(self):
        """Test get a provider with user no group."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token1 = self.get_customer_owner_token(self.customer_data[0])
        create_response = self.create_provider(bucket_name, iam_arn, token1)
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        user_data = self.gen_user_data()
        serializer = UserSerializer(data=user_data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
        token = self.get_token(user_data.get('username'),
                               user_data.get('password'))
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_get_provider_with_anon(self):
        """Test get a provider with anonymous user."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token1 = self.get_customer_owner_token(self.customer_data[0])
        create_response = self.create_provider(bucket_name, iam_arn, token1)
        provider_result = create_response.json()
        provider_uuid = provider_result.get('uuid')
        self.assertIsNotNone(provider_uuid)
        url = reverse('provider-detail', args=[provider_uuid])
        client = APIClient()
        response = client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_create_provider_as_service_admin(self):
        """Test create a provider as service admin."""
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token = self.service_admin_token
        response = self.create_provider(bucket_name, iam_arn, token)
        self.assertEqual(response.status_code, 403)

    def test_remove_provider_with_customer_owner(self):
        """Test removing a provider as the customer owner."""
        # Create Provider with customer owner token
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        customer_owner_token = self.get_token(self.customer_data[0]['owner']['username'],
                                              self.customer_data[0]['owner']['password'])
        response = self.create_provider(bucket_name, iam_arn, customer_owner_token)
        self.assertEqual(response.status_code, 201)

        # Verify that the Provider creation was successful
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('name'),
                         self.customer_data[0].get('name'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'),
                         self.customer_data[0].get('owner').get('username'))

        # Remove Provider with customer token
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=customer_owner_token)
        response = client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_remove_provider_with_regular_user(self):
        """
        Test removing a provider with the user account that created it.

        This user is not a customer owner.
        """
        # Get the customer owner token so a regular user can be created
        user_name = self.customer_data[0]['owner']['username']
        user_pass = self.customer_data[0]['owner']['password']
        customer_owner_token = self.get_token(user_name, user_pass)

        # Create a regular user and get the user's token
        user_data = {'username': 'joe', 'password': 'joespassword', 'email': 'joe@me.com'}
        user = self.create_user(customer_owner_token, user_data)
        self.assertEquals(user.status_code, 201)
        user_token = self.get_token(user_data['username'], user_data['password'])

        # Create a Provider as a regular user
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn, user_token)
        self.assertEqual(response.status_code, 201)

        # Verify that the Provider creation was successful
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('name'),
                         self.customer_data[0].get('name'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'), user_data['username'])

        # Remove Provider as the regular user that created the Provider
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=user_token)
        response = client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_remove_provider_with_non_customer_user(self):
        """
        Test removing a provider with the user account that does not belong to the customer group.

        PermissionDenied is expected.
        """
        # Get the customer owner token so a regular user can be created
        user_name = self.customer_data[0]['owner']['username']
        user_pass = self.customer_data[0]['owner']['password']
        owner_token = self.get_token(user_name, user_pass)

        # Create a regular user and get the user's token
        user_data = {'username': 'james', 'password': 'jamespassword', 'email': 'james@me.com'}
        user = self.create_user(owner_token, user_data)
        self.assertEquals(user.status_code, 201)
        user_token = self.get_token(user_data['username'], user_data['password'])

        # Create a Provider as a regular user
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn, user_token)
        self.assertEqual(response.status_code, 201)

        # Verify that the Provider creation was successful
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('name'),
                         self.customer_data[0].get('name'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'), user_data['username'])

        # Create a regular user that belongs to a different customer
        other_owner_token = self.get_token(self.customer_data[1]['owner']['username'],
                                           self.customer_data[1]['owner']['password'])

        other_user_data = {'username': 'sally', 'password': 'sallypassword', 'email': 'sally@me.com'}
        other_user = self.create_user(other_owner_token, other_user_data)
        self.assertEquals(other_user.status_code, 201)
        other_user_token = self.get_token(other_user_data['username'], other_user_data['password'])

        # Remove Provider as the regular user that belongs to the other company
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=other_user_token)
        response = client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_remove_provider_with_reg_user_same_company_didnt_create(self):
        """
        Test removing a provider by a regular user of the same company but did not create the provider.

        PermissionDenied is expected.
        """
        # Get the customer owner token so a regular user can be created
        user_name = self.customer_data[0]['owner']['username']
        user_pass = self.customer_data[0]['owner']['password']
        owner_token = self.get_token(user_name, user_pass)

        # Create a regular user and get the user's token
        user_data = {'username': 'james', 'password': 'jamespassword', 'email': 'james@me.com'}
        user = self.create_user(owner_token, user_data)
        self.assertEquals(user.status_code, 201)
        user_token = self.get_token(user_data['username'], user_data['password'])

        # Create a Provider as a regular user
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        response = self.create_provider(bucket_name, iam_arn, user_token)
        self.assertEqual(response.status_code, 201)

        # Verify that the Provider creation was successful
        json_result = response.json()
        self.assertIsNotNone(json_result.get('uuid'))
        self.assertIsNotNone(json_result.get('customer'))
        self.assertEqual(json_result.get('customer').get('name'),
                         self.customer_data[0].get('name'))
        self.assertIsNotNone(json_result.get('created_by'))
        self.assertEqual(json_result.get('created_by').get('username'), user_data['username'])

        # Create another regular user and get the user's token
        other_user_data = {'username': 'sally', 'password': 'sallypassword', 'email': 'sally@me.com'}
        other_user = self.create_user(owner_token, other_user_data)
        self.assertEquals(other_user.status_code, 201)
        other_user_token = self.get_token(other_user_data['username'], other_user_data['password'])

        # Remove Provider as a regular user that belongs to the same company but did not create the Provider
        url = reverse('provider-detail', args=[json_result.get('uuid')])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=other_user_token)
        response = client.delete(url)
        self.assertEqual(response.status_code, 403)
