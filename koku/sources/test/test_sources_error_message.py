#
# Copyright 2020 Red Hat, Inc.
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
                "key": ProviderErrors.AWS_RESOURCE_NAME_UNREACHABLE,
                "internal_message": "internal resource name message string",
                "expected_message": ProviderErrors.AWS_RESOURCE_NAME_UNREACHABLE_MESSAGE,
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
            key = test.get("key")
            message = test.get("internal_message")
            error = ValidationError(error_obj(key, message))
            message_obj = SourcesErrorMessage(error)
            self.assertEquals(message_obj.display(source_id=1), test.get("expected_message"))

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
                "internal_message": ", AdalError: Get Token request returned http error: 400 and server response:",
                "expected_message": ProviderErrors.AZURE_INCORRECT_CLIENT_ID_MESSAGE,
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
            key = test.get("key")
            message = test.get("internal_message")
            error = ValidationError(error_obj(key, message))
            message_obj = SourcesErrorMessage(error)
            self.assertEquals(message_obj.display(source_id=1), test.get("expected_message"))

    def test_general_string_error(self):
        """Test general string error fallback."""
        random_error_dict = {"rando": "error"}
        message_obj = SourcesErrorMessage(random_error_dict)
        self.assertEquals(message_obj.display(source_id=1), str(random_error_dict))

    def test_available_source(self):
        """Test an available source message."""
        message_obj = SourcesErrorMessage(None).display(source_id=1)
        self.assertEquals(message_obj, "")
