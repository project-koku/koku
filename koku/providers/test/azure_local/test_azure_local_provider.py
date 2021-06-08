#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the AzureLocalProvider implementation for the Koku interface."""
from django.test import TestCase
from faker import Faker
from rest_framework.exceptions import ValidationError

from api.models import Provider
from providers.azure_local.provider import AzureLocalProvider

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
