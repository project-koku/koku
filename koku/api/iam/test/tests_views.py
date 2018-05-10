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
"""Test the IAM views"""

from django.urls import reverse
from django.test import TestCase

from rest_framework.test import APIClient

from ..model import User
from ..serializers import CustomerSerializer, \
                          UserSerializer

from .iam_test_case import IamTestCase

class CustomerViewTest(IamTestCase):
    """Tests the customer view."""

    def setUp(self):
        super().setUp()

        # create a user to reference in the 'owner' field
        for idx, user in enumerate(self.user_data):
            serializer = UserSerializer(data=user)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
            self.customer_data[idx]['owner'] = User.objects.get(pk=idx+1)

        for customer in self.customer_data:
            serial = CustomerSerializer(data=customer)
            if serial.is_valid(raise_exception=True):
                serial.save()

    def test_get_customer_list(self):
        """Test get customer list."""
        url = reverse('customer-list')
        response = APIClient().get(url)
        json_result = response.json()

        self.assertEqual(len(json_result), 2)
        self.assertEqual(json_result[0]['name'], self.customer_data[0]['name'])
        self.assertEqual(json_result[1]['name'], self.customer_data[1]['name'])


    def test_get_customer_detail(self):
        """Test get customer detail."""
        url = reverse('customer-detail', args=[2])
        response = APIClient().get(url)
        json_result = response.json()

        self.assertEqual(json_result['name'], self.customer_data[1]['name'])
        self.assertEqual(json_result['owner'], User.objects.get(pk=2).id)
        self.assertRegex(json_result['customer_id'], r'\w{8}-(\w{4}-){3}\w{12}')

class UserViewTest(IamTestCase):
    """Tests the user view."""

    def setUp(self):
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

        self.assertEqual(len(json_result), 2)
        self.assertEqual(json_result[0]['username'],
                         self.user_data[0]['username'])
        self.assertEqual(json_result[1]['username'],
                         self.user_data[1]['username'])


    def test_get_user_detail(self):
        """Test get user detail."""
        url = reverse('user-detail', args=[2])
        response = APIClient().get(url)
        json_result = response.json()
        print(json_result)

        self.assertEqual(json_result['username'], self.user_data[1]['username'])
        # FIXME: we shouldn't store or expose plain-text passwords
        self.assertEqual(json_result['password'], self.user_data[1]['password'])
        self.assertEqual(json_result['email'], self.user_data[1]['email'])
        self.assertEqual(json_result['first_name'], self.user_data[1]['first_name'])
        self.assertEqual(json_result['last_name'], self.user_data[1]['last_name'])
