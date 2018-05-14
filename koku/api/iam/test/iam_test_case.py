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
"""Test Case extension to collect common test data"""
import logging

from django.urls import reverse
from django.test import TestCase

from faker import Faker
from random import randint

from rest_framework.test import APIClient

from ..model import Customer, User

# prevent faker from spamming logs
# see: https://github.com/joke2k/faker/issues/753
logging.getLogger('faker.factory').setLevel(logging.ERROR)

class IamTestCase(TestCase):
    """Abstract Class for sharing test data"""

    service_admin_token = None

    def setUp(self):
        """Creates test case objects."""
        self.customer_data = [{'name' : 'test_customer_1',
                               'owner': self.gen_user_data()},
                              {'name' : 'test_customer_2',
                               'owner': self.gen_user_data()}]

    def tearDown(self):
        """Tears down test case objects."""
        User.objects.filter(username='service_user').all().delete()

    def get_token(self, username, password):  # pylint: disable=R0201
        """Gets the token for the user."""
        url = reverse('token-auth')
        body = {'username': username,
                'password': password}
        response = APIClient().post(url, body, format='json')
        json_result = response.json()
        token = json_result.get('token')
        return 'Token {}'.format(token)

    def create_service_admin(self):
        """Create a service admin."""
        User.objects.create_superuser(username='service_user',
                                      email='service_user@foo.com',
                                      password='service_pass')
        self.service_admin_token = self.get_token('service_user',
                                                  'service_pass')

    def create_customer(self, customer_data):
        """Create a customer."""
        url = reverse('customer-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=self.service_admin_token)
        response = client.post(url, data=customer_data, format='json')
        return response

    def get_customer_owner_token(self, customer):
        """Get the token for the customer owner."""
        token = None
        owner = customer.get('owner')
        if owner is None:
            return token
        username = owner.get('username')
        password = owner.get('password')
        if username and password:
            token = self.get_token(username, password)
        return token

    def create_user(self, customer_owner_token, user_data):
        """Create a user."""
        url = reverse('user-list')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=customer_owner_token)
        response = client.post(url, data=user_data, format='json')
        return response

    def gen_user_data(self):
        """Generate user data."""
        fake = Faker()
        user_data = {'username': fake.user_name(),
                     'password': fake.password(length=randint(8, 12),
                                               special_chars=True,
                                               digits=True,
                                               upper_case=True,
                                               lower_case=True),
                     'first_name': fake.first_name(),
                     'last_name': fake.last_name(),
                     'email': fake.email()}
        return user_data
