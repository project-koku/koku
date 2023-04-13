#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources Error Message."""
import logging

from rest_framework.serializers import ValidationError

from providers.provider_errors import ProviderErrors

LOG = logging.getLogger(__name__)


class SourcesErrorMessage:
    """Sources Error Message for Sources API service."""

    def __init__(self, error):
        """Initialize the message generator."""
        self._error = error

    def azure_client_errors(self, message):
        """Azure client error messages."""
        scrubbed_message = ProviderErrors.AZURE_GENERAL_CLIENT_ERROR_MESSAGE
        if any(test in message for test in ["http error: 401", "Authentication failed", "(401) Unauthorized"]):
            scrubbed_message = ProviderErrors.AZURE_INCORRECT_CLIENT_SECRET_MESSAGE
        if "AADSTS700016" in message:
            scrubbed_message = ProviderErrors.AZURE_INCORRECT_CLIENT_ID_MESSAGE
        if "AADSTS90002" in message:
            scrubbed_message = ProviderErrors.AZURE_INCORRECT_TENANT_ID_MESSAGE
        if "AADSTS7000222" in message:
            scrubbed_message = ProviderErrors.AZURE_EXPIRED_CLIENT_SECRET_KEYS_MESSAGE
        if "ResourceGroupNotFound" in message:
            scrubbed_message = ProviderErrors.AZURE_INCORRECT_RESOURCE_GROUP_MESSAGE
        if "ResourceNotFound" in message:
            scrubbed_message = ProviderErrors.AZURE_INCORRECT_STORAGE_ACCOUNT_MESSAGE
        if any(test in message for test in ["SubscriptionNotFound", "InvalidSubscriptionId"]):
            scrubbed_message = ProviderErrors.AZURE_INCORRECT_SUBSCRIPTION_ID_MESSAGE
        return scrubbed_message

    def aws_client_errors(self, message):
        """AWS client error messages."""
        return ProviderErrors.AWS_ROLE_ARN_UNREACHABLE_MESSAGE

    def aws_no_billing_source(self, message):
        """AWS no bucket message."""
        return ProviderErrors.AWS_BILLING_SOURCE_NOT_FOUND_MESSAGE

    def aws_invalid_report_compression(self, message):
        """AWS invalid compression message."""
        return ProviderErrors.AWS_COMPRESSION_REPORT_CONFIG_MESSAGE

    def _display_string_function(self, key):
        """Return function to get user facing string."""
        ui_function_map = {
            ProviderErrors.AZURE_CLIENT_ERROR: self.azure_client_errors,
            ProviderErrors.AWS_ROLE_ARN_UNREACHABLE: self.aws_client_errors,
            ProviderErrors.AWS_BILLING_SOURCE_NOT_FOUND: self.aws_no_billing_source,
            ProviderErrors.AWS_COMPRESSION_REPORT_CONFIG: self.aws_invalid_report_compression,
        }
        string_function = ui_function_map.get(key)
        return string_function

    def _extract_from_validation_error(self):
        """Extract key and message from ValidationError."""
        err_key = None
        err_msg = None
        if isinstance(self._error, ValidationError):
            err_dict = self._error.detail
            LOG.info(f"validation error: {self._error}. Validation detail {err_dict}")
            err_key = list(err_dict).pop()
            try:
                err_body = err_dict.get(err_key, []).pop()
            except (TypeError, IndexError):
                err_msg = str(self._error.detail).encode().decode("UTF-8")
            else:
                err_msg = err_body.encode().decode("UTF-8")

        return err_key, err_msg

    def display(self, source_id):
        """Generate user friendly message."""
        display_message = None
        if self._error:
            if isinstance(self._error, ValidationError):
                key, internal_message = self._extract_from_validation_error()
                display_fn = self._display_string_function(key)
                if display_fn:
                    display_message = display_fn(internal_message)
                    LOG.warning(f"Source ID: {source_id} Internal message: {internal_message}.")
                else:
                    display_message = internal_message
            else:
                display_message = str(self._error)
            LOG.warning(f"Source ID: {source_id} error message: {display_message}")
        else:
            display_message = ""
            LOG.info(f"Source ID: {source_id} is available.")

        return display_message
