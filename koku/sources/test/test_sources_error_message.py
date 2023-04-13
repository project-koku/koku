#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Sources Error Messages."""
from django.test import TestCase
from rest_framework.serializers import ValidationError

from api.common import error_obj
from providers.provider_errors import ProviderErrors
from sources.sources_error_message import SourcesErrorMessage


class SourcesErrorMessageTest(TestCase):
    """Test cases for SourcesErrorMessage."""

    def test_aws_errors(self):
        """Test AWS error types."""
        test_matrix = [
            {
                "key": ProviderErrors.AWS_ROLE_ARN_UNREACHABLE,
                "internal_message": "internal resource name message string",
                "expected_message": ProviderErrors.AWS_ROLE_ARN_UNREACHABLE_MESSAGE,
            },
            {
                "key": ProviderErrors.AWS_BILLING_SOURCE_NOT_FOUND,
                "internal_message": "internal billing source message string",
                "expected_message": ProviderErrors.AWS_BILLING_SOURCE_NOT_FOUND_MESSAGE,
            },
            {
                "key": ProviderErrors.AWS_COMPRESSION_REPORT_CONFIG,
                "internal_message": "internal compression error message",
                "expected_message": ProviderErrors.AWS_COMPRESSION_REPORT_CONFIG_MESSAGE,
            },
            {
                "key": ProviderErrors.AWS_BUCKET_MISSING,
                "internal_message": ProviderErrors.AWS_BUCKET_MISSING_MESSAGE,
                "expected_message": ProviderErrors.AWS_BUCKET_MISSING_MESSAGE,
            },
        ]
        for test in test_matrix:
            with self.subTest(test=test):
                key = test.get("key")
                message = test.get("internal_message")
                error = ValidationError(error_obj(key, message))
                message_obj = SourcesErrorMessage(error)
                self.assertEqual(message_obj.display(source_id=1), test.get("expected_message"))

    def test_azure_errors(self):
        """Test Azure error types."""
        test_matrix = [
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": ", AdalError: Get Token request returned http error: 401 and server response:",
                "expected_message": ProviderErrors.AZURE_INCORRECT_CLIENT_SECRET_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": "Authentication failed",
                "expected_message": ProviderErrors.AZURE_INCORRECT_CLIENT_SECRET_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": (
                    "(401) Unauthorized. Request ID: cca1a5a4-4107-4e7a-b3b4-b88f31e6a674\n"
                    "Code: 401\nMessage: Unauthorized. Request ID: cca1a5a4-4107-4e7a-b3b4-b88f31e6a674"
                ),
                "expected_message": ProviderErrors.AZURE_INCORRECT_CLIENT_SECRET_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": (
                    ", AdalError: Get Token request returned http error: 400 and server response:"
                    ' {"error":"invalid_request","error_description":"AADSTS90002: Tenant'
                ),
                "expected_message": ProviderErrors.AZURE_INCORRECT_TENANT_ID_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": (
                    ", AdalError: Get Token request returned http error: 400 and server response:"
                    ' {"error":"unauthorized_client","error_description":"AADSTS700016:'
                ),
                "expected_message": ProviderErrors.AZURE_INCORRECT_CLIENT_ID_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": (
                    "Authentication failed: AADSTS7000222: The provided client secret keys for app"
                    " '84ed5026-61c8-42a3-9511-74735a5c6be2' are expired."
                ),
                "expected_message": ProviderErrors.AZURE_EXPIRED_CLIENT_SECRET_KEYS_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": (
                    "Azure Error: ResourceGroupNotFound\nMessage: Resource group" "'RG2' could not be found."
                ),
                "expected_message": ProviderErrors.AZURE_INCORRECT_RESOURCE_GROUP_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": (
                    "Azure Error: ResourceNotFound\nMessage: The "
                    "Resource 'Microsoft.Storage/storageAccounts/mysa5' under "
                    "resource group 'RG1' was not found"
                ),
                "expected_message": ProviderErrors.AZURE_INCORRECT_STORAGE_ACCOUNT_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": (
                    "Azure Error: SubscriptionNotFound\nMessage: The "
                    "subscription '2639de71-ca37-4a17-a104-17665a50e7fd'"
                    " could not be found."
                ),
                "expected_message": ProviderErrors.AZURE_INCORRECT_SUBSCRIPTION_ID_MESSAGE,
            },
            {
                "key": ProviderErrors.AZURE_CLIENT_ERROR,
                "internal_message": "Random azure error",
                "expected_message": ProviderErrors.AZURE_GENERAL_CLIENT_ERROR_MESSAGE,
            },
        ]
        for test in test_matrix:
            with self.subTest(test=test):
                key = test.get("key")
                message = test.get("internal_message")
                error = ValidationError(error_obj(key, message))
                message_obj = SourcesErrorMessage(error)
                self.assertEqual(message_obj.display(source_id=1), test.get("expected_message"))

    def test_general_string_error(self):
        """Test general string error fallback."""
        random_error_dict = {"rando": "error"}
        message_obj = SourcesErrorMessage(random_error_dict)
        self.assertEqual(message_obj.display(source_id=1), str(random_error_dict))

    def test_available_source(self):
        """Test an available source message."""
        message_obj = SourcesErrorMessage(None).display(source_id=1)
        self.assertEqual(message_obj, "")

    def test_error_details_are_dict(self):
        err_dict = {
            "billing_source": {
                "data_source": {
                    "provider.data_source": [
                        (
                            'ErrorDetail(string="One or more required fields is invalid/missing. '
                            "Required fields are ['bucket']\", code='invalid')"
                        )
                    ]
                }
            }
        }
        error = ValidationError(err_dict)
        message_obj = SourcesErrorMessage(error)
        message = message_obj.display(source_id=1)

        self.assertIn(message, ProviderErrors.AWS_BUCKET_MISSING)
