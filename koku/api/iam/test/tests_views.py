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
"""Test the IAM views."""

from django.urls import reverse
from rest_framework.test import APIClient

from .iam_test_case import IamTestCase
from ..models import Customer, User
from ..serializers import CustomerSerializer, UserSerializer


class CustomerViewTest(IamTestCase):
    """Tests the customer view."""

    service_admin_token = None

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        User.objects.create_superuser(username='service_user',
                                      email='service_user@foo.com',
                                      password='service_pass')
        url = reverse('token-auth')
        body = {'username': 'service_user',
                'password': 'service_pass'}
        response = APIClient().post(url, body, format='json')
        json_result = response.json()
        token = json_result.get('token')
        self.service_admin_token = 'Token {}'.format(token)

        for customer in self.customer_data:
            serial = CustomerSerializer(data=customer)
            if serial.is_valid(raise_exception=True):
                serial.save()

    def tearDown(self):
        """Tear down the customer view tests."""
        User.objects.filter(username='service_user').all().delete()

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
                         self.user_data[0]['username'])
        self.assertRegex(json_result['uuid'], r'\w{8}-(\w{4}-){3}\w{12}')


class UserViewTest(IamTestCase):
    """Tests the user view."""

    def setUp(self):
        """Set up the user view tests."""
        super().setUp()

        # create the users to test
        for user in self.user_data:
            serializer = UserSerializer(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_get_user_list(self):
        """Test get user list."""
        url = reverse('user-list')
        response = APIClient().get(url)
        json_result = response.json()

        results = json_result.get('results')
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['username'],
                         self.user_data[1]['username'])
        self.assertEqual(results[1]['username'],
                         self.user_data[0]['username'])

    def test_get_user_detail(self):
        """Test get user detail."""
        first = User.objects.first()
        url = reverse('user-detail', args=[first.uuid])
        response = APIClient().get(url)
        json_result = response.json()

        self.assertEqual(json_result['username'], first.username)
        self.assertEqual(json_result['email'], first.email)
        # ensure passwords don't leak
        self.assertIsNone(json_result.get('password'))
