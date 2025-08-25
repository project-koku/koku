#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Azure Provider."""
from unittest.mock import MagicMock
from unittest.mock import patch

from azure.common import AzureException
from django.test import TestCase
from faker import Faker
from rest_framework.serializers import ValidationError

from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from providers.azure.provider import AzureProvider
from providers.provider_errors import ProviderErrors

FAKE = Faker()


def throws_azure_nocosterror():
    """Raise error for testing."""
    raise AzureCostReportNotFound()


class AzureProviderTestCase(TestCase):
    """Parent Class for AzureClientFactory test cases."""

    def setUp(self):
        """Create test case objects."""
        super().setUp()
        self.source = MagicMock(
            return_value={
                "billing_source": {
                    "data_source": {
                        "resource_group": FAKE.word(),
                        "storage_account": FAKE.word(),
                        "storage_only": True,
                    }
                },
                "authentication": {
                    "credentials": {
                        "subscription_id": FAKE.uuid4(),
                        "tenant_id": FAKE.uuid4(),
                        "client_id": FAKE.uuid4(),
                        "client_secret": FAKE.word(),
                    }
                },
            }
        )
        self.files = ["test_file.csv"]

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
            mock_return_value = [{"type": "ActualCost"}]
            MockHelper.return_value.describe_cost_management_exports.return_value = mock_return_value

            obj = AzureProvider()
            self.assertTrue(obj.cost_usage_source_is_reachable(credentials, source_name))

    @patch("providers.azure.provider.AzureService", side_effect=AzureException("test exception"))
    def test_cost_usage_source_is_reachable_exception(self, _):
        """Test that ValidationError is raised when AzureException is raised."""
        subscription_id = FAKE.uuid4()
        scope = f"subscriptions/{subscription_id}"
        credentials = {
            "subscription_id": subscription_id,
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word(), "scope": scope}
        with self.assertRaises(ValidationError):
            AzureProvider().cost_usage_source_is_reachable(credentials, source_name)

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

    def test_cost_usage_source_is_reachable_specific_badargs(self):
        """Test various ValidationErrors in _verify_patch_entries."""
        fake_word = FAKE.word()

        test_table = [
            {
                "args": {
                    "data_source": {"scope": fake_word},
                    "credentials": {},
                },
                "expected": ProviderErrors.AZURE_MISSING_EXPORT_NAME_MESSAGE,
            },
            {
                "args": {
                    "data_source": {"scope": fake_word, "export_name": fake_word},
                    "credentials": {},
                },
                "expected": ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_AND_STORAGE_ACCOUNT_MESSAGE,
            },
            {
                "args": {
                    "data_source": {},
                    "credentials": {"subscription_id": fake_word},
                },
                "expected": ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_AND_STORAGE_ACCOUNT_MESSAGE,
            },
            {
                "args": {
                    "data_source": {"scope": fake_word, "export_name": fake_word, "resource_group": fake_word},
                    "credentials": {},
                },
                "expected": ProviderErrors.AZURE_MISSING_STORAGE_ACCOUNT_MESSAGE,
            },
            {
                "args": {
                    "data_source": {"resource_group": fake_word},
                    "credentials": {"subscription_id": fake_word},
                },
                "expected": ProviderErrors.AZURE_MISSING_STORAGE_ACCOUNT_MESSAGE,
            },
            {
                "args": {
                    "data_source": {"scope": fake_word, "export_name": fake_word, "storage_account": fake_word},
                    "credentials": {},
                },
                "expected": ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_MESSAGE,
            },
            {
                "args": {
                    "data_source": {"storage_account": fake_word},
                    "credentials": {"subscription_id": fake_word},
                },
                "expected": ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_MESSAGE,
            },
            {
                "args": {
                    "data_source": {"resource_group": fake_word, "storage_account": fake_word},
                    "credentials": {},
                },
                "expected": ProviderErrors.AZURE_MISSING_SUBSCRIPTION_ID_MESSAGE,
            },
            {
                "args": {
                    "data_source": {},
                    "credentials": {},
                },
                "expected": ProviderErrors.AZURE_MISSING_ALL_PATCH_VALUES_MESSAGE,
            },
        ]

        for test in test_table:
            with self.subTest(test["expected"]):
                with self.assertRaises(ValidationError) as exc:
                    AzureProvider().cost_usage_source_is_reachable(**test["args"])
                self.assertIn(test["expected"], str(exc.exception))

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

    # Written as separate tests for atomic testing
    # These two tests could be combined with pytest.parametrize
    @patch("providers.azure.provider.AzureClientFactory")
    def test_cost_usage_source_reachable_value_error(self, mock_azure_factory):
        """Test that cost_usage_source_is_reachable raises the correct exception when a ValueError is raised"""
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}
        azure_provider = AzureProvider()

        with patch("providers.azure.provider.AzureService", side_effect=ValueError("Raised intentionally")):
            with self.assertRaisesRegex(ValidationError, "Raised intentionally"):
                azure_provider.cost_usage_source_is_reachable(credentials, source_name)

    @patch("providers.azure.provider.AzureClientFactory")
    def test_cost_usage_source_reachable_type_error(self, mock_azure_factory):
        """Test that cost_usage_source_is_reachable raises the correct exception when a TypeError is raised"""
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}
        azure_provider = AzureProvider()

        with patch("providers.azure.provider.AzureService", side_effect=TypeError("Raised intentionally")):
            with self.assertRaisesRegex(ValidationError, "Raised intentionally"):
                azure_provider.cost_usage_source_is_reachable(credentials, source_name)

    @patch("providers.azure.provider.AzureClientFactory")
    def test_storage_only_source_is_created(self, mock_azure_factory):
        """Verify that a storage only sources is created."""
        provider_interface = AzureProvider()
        try:
            credentials = {
                "subscription_id": FAKE.uuid4(),
                "tenant_id": FAKE.uuid4(),
                "client_id": FAKE.uuid4(),
                "client_secret": FAKE.word(),
            }
            data_source = {"resource_group": FAKE.word(), "storage_account": FAKE.word(), "storage_only": True}
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
        except Exception:
            self.fail("Unexpected Error")

    @patch("providers.azure.provider.AzureClientFactory")
    def test_is_file_reachable_valid(self, mock_azure_client):
        """Test that ingress file is reachable."""
        provider_interface = AzureProvider()
        provider_interface.is_file_reachable(self.source, self.files)
        mock_azure_client.cloud_storage_account.get_blob_client.assert_called

    @patch("providers.azure.client.AzureClientFactory")
    def test_is_file_reachable_authentication_error(self, mock_azure_client):
        """Test ingress file check azure authentication error."""
        err_msg = "Azure Error"
        mock_azure_client.side_effect = AzureException(err_msg)
        with self.assertRaises(ValidationError):
            provider_interface = AzureProvider()
            provider_interface.is_file_reachable(self.source, self.files)

    @patch("providers.azure.provider.AzureClientFactory")
    def test_cost_usage_source_is_reachable_unsupported_type(self, _):
        """Test that a ValidationError is raised for an unsupported report type."""
        credentials = {
            "subscription_id": FAKE.uuid4(),
            "tenant_id": FAKE.uuid4(),
            "client_id": FAKE.uuid4(),
            "client_secret": FAKE.word(),
        }
        source_name = {"resource_group": FAKE.word(), "storage_account": FAKE.word()}
        unsupported_type = "Usage"  # Not supported type

        with patch("providers.azure.provider.AzureService") as MockHelper:
            mock_return_value = [{"type": unsupported_type}]
            MockHelper.return_value.describe_cost_management_exports.return_value = mock_return_value

            azure_provider = AzureProvider()

            with self.assertRaises(ValidationError) as exc:
                azure_provider.cost_usage_source_is_reachable(credentials, source_name)

            expected_msg = f"Unsupported report type: '{unsupported_type}'"
            self.assertIn(expected_msg, str(exc.exception))
