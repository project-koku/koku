#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Azure Provider."""
from unittest.mock import patch

from azure.common import AzureException
from django.test import TestCase
from faker import Faker
from rest_framework.serializers import ValidationError

from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from providers.azure.provider import AzureProvider

FAKE = Faker()


def throws_azure_nocosterror():
    """Raise error for testing."""
    raise AzureCostReportNotFound()


class AzureProviderTestCase(TestCase):
    """Parent Class for AzureClientFactory test cases."""

    def test_name(self):
        """Test name property."""
        obj = AzureProvider()
        self.assertEqual(obj.name(), "Azure")

    @patch("providers.azure.provider.AzureClientFactory")
    def test_cost_usage_source_is_reachable_valid(self, _):
        """Test that cost_usage_source_is_reachable succeeds."""
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}
        with patch("providers.azure.provider.AzureService") as MockHelper:
            MockHelper.return_value.describe_cost_management_exports.return_value = ["report1"]
            obj = AzureProvider()
            self.assertTrue(obj.cost_usage_source_is_reachable(credentials, source_name))

    @patch("providers.azure.provider.AzureClientFactory", side_effect=AzureException("test exception"))
    def test_cost_usage_source_is_reachable_exception(self, _):
        """Test that ValidationError is raised when AzureException is raised."""
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}
        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable(credentials, source_name)

    def test_cost_usage_source_is_reachable_badargs(self):
        """Test that a ValidationError is raised when no arguments are provided."""
        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable(None, None)

        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable(FAKE.word(), FAKE.word())

        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable({}, {})

    def test_infra_type_implementation(self):
        """Test that infra type returns None."""
        obj = AzureProvider()
        self.assertEqual(obj.infra_type_implementation(FAKE.word(), FAKE.word()), None)

    def test_infra_key_list_implementation(self):
        """Test that infra key list returns an empty list."""
        obj = AzureProvider()
        self.assertEqual(obj.infra_key_list_implementation(FAKE.uuid4(), FAKE.word()), [])

    @patch("providers.azure.provider.AzureClientFactory")
    def test_cost_usage_source_reachable_without_cost_export(self, _):
        """Test that cost_usage_source_is_reachable raises an exception when no cost reports exist."""
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}

        with patch("providers.azure.provider.AzureService") as MockHelper:
            MockHelper.return_value.describe_cost_management_exports.return_value = []
            azure_provider = AzureProvider()
            with self.assertRaises(ValidationError):
                azure_provider.cost_usage_source_is_reachable(credentials, source_name)

    @patch("providers.azure.provider.AzureClientFactory")
    def test_cost_usage_source_reachable_no_auth_cost_export(self, _):
        """Test that cost_usage_source_is_reachable raises an exception when no auth to get cost reports."""
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}

        with patch("providers.azure.provider.AzureService") as MockHelper:
            MockHelper.return_value.describe_cost_management_exports.side_effect = throws_azure_nocosterror
            azure_provider = AzureProvider()
            with self.assertRaises(ValidationError):
                azure_provider.cost_usage_source_is_reachable(credentials, source_name)
