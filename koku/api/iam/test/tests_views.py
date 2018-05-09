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


class CustomerViewTest(TestCase):
    """Tests the customer view."""

    def setUp(self):
        user_data = [{'username': 'testy',
                      'password': '12345',
                      'first_name': 'Testy',
                      'last_name': 'McTesterson',
                      'email': 'test@test.foo'},
                     {'username': 'foo',
                      'password': 's3kr1t',
                      'first_name': 'Foo',
                      'last_name': 'Bar',
                      'email': 'foo@foo.bar'}]
        for user in user_data:
            serial = UserSerializer(data=user)
            if serial.is_valid(raise_exception=True):
                serial.save()

        self.data = [{'name': 'Customer1', 'owner': User.objects.get(pk=1)},
                     {'name': 'Customer2', 'owner': User.objects.get(pk=2)}]

        for customer in self.data:
            serial = CustomerSerializer(data=customer)
            if serial.is_valid(raise_exception=True):
                serial.save()

    def test_get_customer_list(self):
        """Test get customer list."""
        url = reverse('customer-list')
        response = APIClient().get(url)
        json_result = response.json()

        self.assertEqual(len(json_result), 2)
        self.assertEqual(json_result[0]['name'], self.data[0]['name'])
        self.assertEqual(json_result[1]['name'], self.data[1]['name'])


    def test_get_customer_detail(self):
        """Test get customer detail."""
        url = reverse('customer-detail', args=[2])
        response = APIClient().get(url)
        json_result = response.json()

        self.assertEqual(json_result['name'], self.data[1]['name'])
