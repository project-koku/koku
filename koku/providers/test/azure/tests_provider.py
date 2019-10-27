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
"""Test Azure Provider."""
from unittest.mock import patch

from azure.common import AzureException
from django.test import TestCase
from faker import Faker
from rest_framework.serializers import ValidationError

from providers.azure.provider import AzureProvider

FAKE = Faker()


class AzureProviderTestCase(TestCase):
    """Parent Class for AzureClientFactory test cases."""

    def test_name(self):
        """Test name property."""
        obj = AzureProvider()
        self.assertEqual(obj.name(), 'Azure')

    @patch('providers.azure.provider.AzureClientFactory')
    def test_cost_usage_source_is_reachable_valid(self, _):
        """Test that cost_usage_source_is_reachable succeeds."""
        credentials = {'subscription_id': FAKE.uuid4(),
                       'tenant_id': FAKE.uuid4(),
                       'client_id': FAKE.uuid4(),
                       'client_secret': FAKE.word()}
        source_name = {'resource_group': FAKE.word(),
                       'storage_account': FAKE.word()}
        obj = AzureProvider()
        self.assertTrue(obj.cost_usage_source_is_reachable(credentials,
                                                           source_name))

    @patch('providers.azure.provider.AzureClientFactory',
           side_effect=AzureException('test exception'))
    def test_cost_usage_source_is_reachable_exception(self, _):
        """Test that ValidationError is raised when AzureException is raised."""
        credentials = {'subscription_id': FAKE.uuid4(),
                       'tenant_id': FAKE.uuid4(),
                       'client_id': FAKE.uuid4(),
                       'client_secret': FAKE.word()}
        source_name = {'resource_group': FAKE.word(),
                       'storage_account': FAKE.word()}
        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable(credentials,
                                                           source_name)

    def test_cost_usage_source_is_reachable_badargs(self):
        """Test that a ValidationError is raised when no arguments are provided."""
        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable(None, None)

        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable(FAKE.word(),
                                                           FAKE.word())

        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable({}, {})

    def test_infra_type_implementation(self):
        """Test that infra type returns None."""
        obj = AzureProvider()
        self.assertEqual(obj.infra_type_implementation(FAKE.word(), FAKE.word()), None)

    def test_infra_key_list_implementation(self):
        """Test that infra key list returns an empty list."""
        obj = AzureProvider()
        self.assertEqual(obj.infra_key_list_implementation(FAKE.uuid4(),
                                                           FAKE.word()), [])
