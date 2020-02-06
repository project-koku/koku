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
"""Tests the AzureLocalProvider implementation for the Koku interface."""
from api.models import Provider
from django.test import TestCase
from faker import Faker
from providers.azure_local.provider import AzureLocalProvider
from rest_framework.exceptions import ValidationError

FAKE = Faker()


class AzureLocalProviderTestCase(TestCase):
    """Parent Class for AzureLocalProvider test cases."""

    def test_get_name(self):
        """Get name of provider."""
        provider = AzureLocalProvider()
        self.assertEqual(provider.name(), Provider.PROVIDER_AZURE_LOCAL)

    def test_cost_usage_source_is_reachable_valid(self):
        """Test that cost_usage_source_is_reachable succeeds."""
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}
        obj = AzureLocalProvider()
        self.assertTrue(obj.cost_usage_source_is_reachable(credentials, source_name))

    def test_cost_usage_source_is_reachable_badargs(self):
        """Test that a ValidationError is raised when no arguments are provided."""
        with self.assertRaises(ValidationError):
            AzureLocalProvider().cost_usage_source_is_reachable(None, None)

        with self.assertRaises(ValidationError):
            AzureLocalProvider().cost_usage_source_is_reachable(FAKE.word(), FAKE.word())

        with self.assertRaises(ValidationError):
            AzureLocalProvider().cost_usage_source_is_reachable({}, {})
