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
"""Azure provider."""
from adal.adal_error import AdalError
from azure.common import AzureException
from django.utils.translation import ugettext as _
from msrest.exceptions import ClientException
from rest_framework.serializers import ValidationError

from api.models import Provider
from masu.external.downloader.azure.azure_service import AzureService, AzureServiceError
from .client import AzureClientFactory
from ..provider_interface import ProviderInterface


def error_obj(key, message):
    """Create an error object."""
    error = {
        key: [_(message)]
    }
    return error


class AzureProvider(ProviderInterface):
    """Azure provider defnition."""

    def name(self):
        """
        Return the provider service's name.

        Implemented by provider specific class to return it's name.

        Args:
            None

        Returns:
            (String) : Name of Service
                       example: "AWS"

        """
        return Provider.PROVIDER_AZURE

    def cost_usage_source_is_reachable(self, credential_name,
                                       storage_resource_name):
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
        key = 'billing_source.bucket'

        azure_service = None

        if not (isinstance(credential_name, dict)
                and isinstance(storage_resource_name, dict)):
            message = f'Resource group and/or Storage account must be a dict'
            raise ValidationError(error_obj(key, message))

        resource_group = storage_resource_name.get('resource_group')
        storage_account = storage_resource_name.get('storage_account')
        if not (resource_group and storage_account):
            message = 'resource_group or storage_account is undefined.'
            raise ValidationError(error_obj(key, message))

        try:
            azure_client = AzureClientFactory(**credential_name)
            storage_accounts = azure_client.storage_client.storage_accounts
            storage_account = storage_accounts.get_properties(resource_group,
                                                              storage_account)
            azure_service = AzureService(**credential_name, resource_group_name=resource_group,
                                         storage_account_name=storage_account)
        except (AdalError, AzureException, AzureServiceError, ClientException, TypeError) as exc:
            raise ValidationError(error_obj(key, str(exc)))

        if azure_service and not azure_service.describe_cost_management_exports():
            message = 'Cost management export was not found.'
            raise ValidationError(error_obj(key, message))

        return True

    def infra_type_implementation(self, provider_uuid, schema_name):
        """
        Return the type of infrastructure the provider is running on.

        Args:
            None

        Returns:
            None

        Raises:
            ProviderAccessorError: Error string

        """
        return None

    def infra_key_list_implementation(self, infrastructure_type, schema_name):
        """
        Return a list of key values.

        Used to identify resources running on provided infrastructure type.

        Args:
            infrastructure_type (String): Provider type
            schema_name (String): Database schema name

        Returns:
            (List) : List of strings
                    example: ['ocp-cluster-on-aws-1', 'ocp-cluster-on-aws-2']

        Raises:
            ProviderAccessorError: Error string

        """
        return []
