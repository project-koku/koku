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
"""Test the token authentication."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api.iam.models import Tenant

USERNAME = 'testuser'
PASSWORD = 'password1'


class TokenTestCase(TestCase):
    """Test Class for the authentication token flow."""

    def setUp(self):
        """Set up the test cases."""
        tenant = Tenant.objects.get_or_create(schema_name='public')

        User.objects.create_user(username=USERNAME,
                                 password=PASSWORD)

    def test_token_endpoint(self):
        """Test the token endpoint for the test user."""
        url = reverse('token-auth')
        body = {'username': USERNAME,
                'password': PASSWORD}
        response = APIClient().post(url, body, format='json')
        json_result = response.json()

        self.assertIsNotNone(json_result.get('token'))

    def test_token_endpoint_invalid(self):
        """Test the token endpoint for an invalid user."""
        url = reverse('token-auth')
        body = {'username': 'baduser',
                'password': 'badpass'}
        response = APIClient().post(url, body, format='json')

        self.assertEqual(response.status_code, 400)
