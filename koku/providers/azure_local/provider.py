#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure-local service provider implementation to be used by Koku."""
from rest_framework.serializers import ValidationError

from ..azure.provider import AzureProvider
from ..provider_errors import ProviderErrors
from api.common import error_obj
from api.models import Provider


class AzureLocalProvider(AzureProvider):
    """Provider interface definition."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_AZURE_LOCAL

    def cost_usage_source_is_reachable(self, credentials, data_source):
        """
        Verify that the cost usage report source is reachable by Koku.

        Implemented by provider specific class.  An account validation and
        connectivity check is to be done.

        Args:
            credentials (dict): Azure credentials dict

            example: {'subscription_id': 'f695f74f-36a4-4112-9fe6-74415fac75a2',
                      'tenant_id': '319d4d72-7ddc-45d0-9d63-a2db0a36e048',
                      'client_id': 'ce26bd50-2e5a-4eb7-9504-a05a79568e25',
                      'client_secret': 'abc123' }

            data_source (dict): Identifier of the cost usage report source

            example: { 'resource_group': 'My Resource Group 1',
                       'storage_account': 'My Storage Account 2'

        Returns:
            None

        Raises:
            ValidationError: Error string

        """
        key = "azure.error"

        if not (isinstance(credentials, dict) and isinstance(data_source, dict)):
            message = "Resource group and/or Storage account must be a dict"
            raise ValidationError(error_obj(key, message))

        resource_group = data_source.get("resource_group")
        storage_account = data_source.get("storage_account")
        if not (resource_group and storage_account):
            message = ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_AND_STORAGE_ACCOUNT_MESSAGE
            raise ValidationError(error_obj(key, message))

        return True
