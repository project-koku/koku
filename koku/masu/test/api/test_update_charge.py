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

"""Test the update_charge endpoint view."""

from unittest.mock import patch
from urllib.parse import urlencode
from django.test import TestCase
from django.urls import reverse
from django.test.utils import override_settings

from masu.test import MasuTestCase

@override_settings(ROOT_URLCONF='masu.urls')
class UpdateChargeTest(TestCase, MasuTestCase):
    """Test Cases for the update_charge endpoint."""

    @patch('masu.api.update_charge.update_charge_info')
    def test_get_update_charge(self, mock_update):
        """Test the GET report_data endpoint."""
        params = {
            'schema': 'acct10001',
            'provider_uuid': '3c6e687e-1a09-4a05-970c-2ccf44b0952e',
        }
        expected_key = 'Update Charge Task ID'

        response = self.client.get(reverse('update_charge'), params)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn(expected_key, body)
        mock_update.delay.assert_called_with(params['schema'], params['provider_uuid'])

    @patch('masu.api.update_charge.update_charge_info')
    def test_get_update_charge_schema_missing(self, mock_update):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        params = {'provider_uuid': '3c6e687e-1a09-4a05-970c-2ccf44b0952e'}
        expected_key = 'Error'
        expected_message = 'provider_uuid and schema_name are required parameters.'

        response = self.client.get(reverse('update_charge'), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)

    @patch('masu.api.update_charge.update_charge_info')
    def test_get_update_charge_provider_missing(self, mock_update):
        """Test GET report_data endpoint returns a 400 for missing schema."""
        params = {'schema': 'acct10001'}
        expected_key = 'Error'
        expected_message = 'provider_uuid and schema_name are required parameters.'

        response = self.client.get(reverse('update_charge'), params)
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertIn(expected_key, body)
        self.assertEqual(body[expected_key], expected_message)
