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
"""Test the Customer views."""

from unittest.mock import patch

from django.contrib.auth.models import User as UserAuth
from django.db import DatabaseError
from django.http import HttpResponse
from django.urls import reverse
from providers.provider_access import ProviderAccess
from rest_framework import mixins
from rest_framework.test import APIClient

from api.provider.models import Provider
from api.provider.provider_manager import ProviderManager, ProviderManagerError
from .iam_test_case import IamTestCase
from ..models import Customer, Tenant, User
from ..serializers import CustomerSerializer


class CustomerViewTest(IamTestCase):
    """Tests the customer view."""

    def _create_regular_users_for_customer(self, customer_uuid, num_users):
        customer_json = None
        for customer in self.customers:
            if customer['uuid'] == str(customer_uuid):
                customer_json = customer

        co_token = customer_json['owner']['token']
        for _ in range(0, num_users):
            a_user = self.gen_user_data()
            user_response = self.create_user(co_token, a_user)
            user_json = user_response.json()
            user_uuid = user_json.get('uuid')
            self.assertIsNotNone(user_uuid)
            a_user['uuid'] = user_uuid
            user_token = self.get_token(a_user['username'],
                                        a_user['password'])
            a_user['token'] = user_token
            customer_json['users'].append(a_user)

    def _create_provider(self, bucket_name, iam_arn, token):
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

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.create_service_admin()
        self.customers = []

        for customer in self.customer_data:
            response = self.create_customer(customer)
            customer_json = response.json()
            self.assertEqual(response.status_code, 201)
            customer_uuid = customer_json.get('uuid')
            owner = customer_json.get('owner')
            self.assertIsNotNone(customer_uuid)
            self.assertIsNotNone(owner)
            co_token = self.get_customer_owner_token(customer)
            owner['token'] = co_token

            customer_json['users'] = []
            customer_json['users'].append(owner)

            self.customers.append(customer_json)

    def tearDown(self):
        """Tear down customers tests."""
        super().tearDown()
        Customer.objects.all().delete()
        User.objects.all().delete()

    def test_get_customer_list(self):
        """Test get customer list."""
        url = reverse('customer-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        response = client.get(url)
        json_result = response.json()

        results = json_result.get('results')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['name'], self.customer_data[0]['name'])
        self.assertEqual(results[1]['name'], self.customer_data[1]['name'])

    def test_get_customer_detail(self):
        """Test get customer detail."""
        first = Customer.objects.first()
        url = reverse('customer-detail', args=[first.uuid])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        response = client.get(url)
        json_result = response.json()

        self.assertEqual(json_result['name'], self.customer_data[0]['name'])
        self.assertEqual(json_result['owner']['username'],
                         self.customer_data[0]['owner']['username'])
        self.assertRegex(json_result['uuid'], r'\w{8}-(\w{4}-){3}\w{12}')

    def test_delete_missing_customer(self):
        """Test to deleting missing customer."""
        non_existint_uuid = '90832104-d697-47bc-bc45-e6c29636dcfb'
        url = reverse('customer-detail', args=[non_existint_uuid])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        response = client.delete(url)
        self.assertEqual(response.status_code, 404)

    def test_delete_customer(self):
        """Test delete customer."""
        customers = Customer.objects.all()
        self.assertIsNotNone(customers)

        customer_count = customers.count()

        customer_to_delete = customers[0]
        url = reverse('customer-detail', args=[customer_to_delete.uuid])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        response = client.delete(url)
        self.assertEqual(response.status_code, 204)

        # Verify that only customer_to_delete was removed
        for customer in customers:
            customer_exists = customer in Customer.objects.all()
            if customer is customer_to_delete:
                self.assertEquals(customer_exists, False)
            else:
                self.assertEquals(customer_exists, True)
        # Sanity check that the customer count was reduced by 1
        self.assertEquals(Customer.objects.all().count(), customer_count - 1)

    def test_delete_customer_with_reg_users_providers(self):
        """Test deleting customers with regular users and providers."""
        customers = self.customers
        self.assertIsNotNone(customers)

        self.assertEquals(len(customers), 2)
        customer_1 = customers[0]
        customer_2 = customers[1]

        # Setup Providers
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token = customer_1['owner']['token']
        response = self._create_provider(bucket_name, iam_arn, token)
        self.assertEqual(response.status_code, 201)

        bucket2_name = 'my_other_s3_bucket'
        iam_arn2 = 'arn:aws:s3:::my_other_s3_bucket'

        response = self._create_provider(bucket2_name, iam_arn2, token)
        self.assertEqual(response.status_code, 201)

        # Verify providers are created
        provider_url = reverse('provider-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(provider_url)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        results = json_result.get('results')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 2)
        provider_uuids = [provider['uuid'] for provider in results]

        # Verify that customer_1 providers are  in the database
        for uuid in provider_uuids:
            self.assertTrue(Provider.objects.filter(uuid=uuid).exists())

        # Setup Regular users
        self._create_regular_users_for_customer(customer_1['uuid'], 3)
        self._create_regular_users_for_customer(customer_2['uuid'], 2)

        url = reverse('customer-detail', args=[customer_1['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        response = client.delete(url)
        self.assertEqual(response.status_code, 204)

        # Verify customer_1 users are gone
        token = customer_1['owner']['token']
        url = reverse('user-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)

        # Returning 401 because the customer token has been destroyed
        self.assertEqual(response.status_code, 401)

        json_result = response.json()
        results = json_result.get('results')
        self.assertIsNone(results)

        # Verify that customer_1 and it's users are not in the database
        self.assertFalse(Customer.objects.filter(uuid=customer_1['uuid']).exists())

        for user in customer_1['users']:
            self.assertFalse(User.objects.filter(uuid=user['uuid']).exists())

        # Verify that customer_1 providers are not in the database
        for uuid in provider_uuids:
            self.assertFalse(Provider.objects.filter(uuid=uuid).exists())

        # Verify customer_2 users are still intact
        token = customer_2['owner']['token']
        url = reverse('user-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=token)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

        json_result = response.json()
        results = json_result.get('results')
        self.assertIsNotNone(results)

        sorted_users = sorted(customer_2['users'],
                              key=lambda user: user['username'])
        user_count = len(sorted_users)
        self.assertEqual(len(results), user_count)
        for useridx in range(0, user_count):
            self.assertEqual(results[useridx]['username'],
                             sorted_users[useridx]['username'])

        # Verify that customer_2 and it's users are not in the database
        self.assertTrue(Customer.objects.filter(uuid=customer_2['uuid']).exists())

        for user in customer_2['users']:
            self.assertTrue(User.objects.filter(uuid=user['uuid']).exists())

    def test_delete_customer_user_del_exception(self):
        """Test customer deletion with regular user deletion exception."""
        customer_1 = self.customers[0]
        self.assertIsNotNone(customer_1)

        # Setup Regular users
        self._create_regular_users_for_customer(customer_1['uuid'], 3)

        url = reverse('customer-detail', args=[customer_1['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        with patch.object(UserAuth, 'delete', side_effect=DatabaseError):
            response = client.delete(url)
        self.assertEqual(response.status_code, 500)

    def test_delete_customer_provider_del_exception(self):
        """Test customer deletion with provider deletion exception."""
        customer_1 = self.customers[0]
        self.assertIsNotNone(customer_1)

        # Setup Providers
        iam_arn = 'arn:aws:s3:::my_s3_bucket'
        bucket_name = 'my_s3_bucket'
        token = customer_1['owner']['token']
        response = self._create_provider(bucket_name, iam_arn, token)
        self.assertEqual(response.status_code, 201)

        url = reverse('customer-detail', args=[customer_1['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        with patch.object(ProviderManager, 'remove', side_effect=ProviderManagerError('fake')):
            response = client.delete(url)
        self.assertEqual(response.status_code, 500)

    def test_delete_customer_exception(self):
        """Test customer deletion with deletion exception."""
        customer_1 = self.customers[0]
        self.assertIsNotNone(customer_1)

        # Setup Regular users
        self._create_regular_users_for_customer(customer_1['uuid'], 3)

        url = reverse('customer-detail', args=[customer_1['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)

        mock_response = HttpResponse(status=500, reason='Mock Internal Error')
        with patch.object(mixins.DestroyModelMixin, 'destroy', return_value=mock_response):
            response = client.delete(url)
        self.assertEqual(response.status_code, 500)

        # Verify that all users still exist even though customer deletion failed.
        for user in customer_1['users']:
            self.assertTrue(User.objects.filter(uuid=user['uuid']).exists())

    def test_delete_customer_exception_missing_group(self):
        """Test customer deletion with deletion exception."""
        customer_1 = self.customers[0]
        self.assertIsNotNone(customer_1)

        # Setup Regular users
        self._create_regular_users_for_customer(customer_1['uuid'], 3)

        url = reverse('customer-detail', args=[customer_1['uuid']])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        with patch.object(CustomerSerializer, 'get_users_for_group', return_value=None):
            response = client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_delete_customer_with_tenant(self):
        """Test customer deletion with associated tenant data."""
        # Create a customer with tenant data.
        customer_name = 'test_customer_tenant'
        customer_json = {'name': customer_name,
                         'owner': self.gen_user_data()}

        response = self.create_customer_with_tenant(customer_json)
        customer_json = response.json()
        self.assertEqual(response.status_code, 201)
        customer_uuid = customer_json.get('uuid')
        owner = customer_json.get('owner')
        self.assertIsNotNone(customer_uuid)
        self.assertIsNotNone(owner)

        # Verify that the tenant data exists.
        customer_obj = Customer.objects.filter(name=customer_name).get()
        customer_schema_name = customer_obj.schema_name
        tenant_obj = Tenant.objects.filter(schema_name=customer_schema_name).get()
        self.assertIsNotNone(tenant_obj)

        # Remove customer
        url = reverse('customer-detail', args=[customer_obj.uuid])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        response = client.delete(url)
        self.assertEqual(response.status_code, 204)

        # Verify customer was deleted
        self.assertFalse(customer_obj in Customer.objects.all())

        # Verify that the tenant data has been removed
        deleted_tenant_query = Tenant.objects.filter(schema_name=customer_schema_name)
        self.assertEquals(len(deleted_tenant_query), 0)
