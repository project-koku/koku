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
"""Azure-local service provider implementation to be used by Koku."""
import logging

from rest_framework.serializers import ValidationError

from ..azure.provider import AzureProvider
from ..provider_errors import ProviderErrors
from api.common import error_obj
from api.models import Provider

LOG = logging.getLogger(__name__)


class AzureLocalProvider(AzureProvider):
    """Provider interface definition."""

    def name(self):
        """Return name of the provider."""
        return Provider.PROVIDER_AZURE_LOCAL

    def cost_usage_source_is_reachable(self, credential_name, storage_resource_name):
        """
        Verify that the cost usage report source is reachable by Koku.

        Implemented by provider specific class.  An account validation and
        connectivity check is to be done.

        Args:
            credential (dict): Azure credentials dict

            example: {'subscription_id': 'f695f74f-36a4-4112-9fe6-74415fac75a2',
                      'tenant_id': '319d4d72-7ddc-45d0-9d63-a2db0a36e048',
                      'client_id': 'ce26bd50-2e5a-4eb7-9504-a05a79568e25',
                      'client_secret': 'abc123' }

            source_name (dict): Identifier of the cost usage report source

            example: { 'resource_group': 'My Resource Group 1',
                       'storage_account': 'My Storage Account 2'

        Returns:
            None

        Raises:
            ValidationError: Error string

        """
        key = "billing_source.bucket"

        if not (isinstance(credential_name, dict) and isinstance(storage_resource_name, dict)):
            message = "Resource group and/or Storage account must be a dict"
            raise ValidationError(error_obj(key, message))

        resource_group = storage_resource_name.get("resource_group")
        storage_account = storage_resource_name.get("storage_account")
        if not (resource_group and storage_account):
            message = ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_AND_STORAGE_ACCOUNT_MESSAGE
            raise ValidationError(error_obj(key, message))

        return True
