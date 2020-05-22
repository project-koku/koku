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
import logging

from adal.adal_error import AdalError
from azure.common import AzureException
from msrest.exceptions import ClientException
from rest_framework.serializers import ValidationError

from ..provider_errors import ProviderErrors
from ..provider_interface import ProviderInterface
from .client import AzureClientFactory
from api.common import error_obj
from api.models import Provider
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.azure.azure_service import AzureService
from masu.external.downloader.azure.azure_service import AzureServiceError

LOG = logging.getLogger(__name__)


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

    def _verify_patch_entries(self, subscription_id, resource_group, storage_account):
        """Raise Validation Error for missing."""
        if subscription_id and not (resource_group and storage_account):
            key = ProviderErrors.AZURE_MISSING_PATCH
            message = ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_AND_STORAGE_ACCOUNT_MESSAGE
            raise ValidationError(error_obj(key, message))

        if subscription_id and resource_group and not storage_account:
            key = ProviderErrors.AZURE_MISSING_PATCH
            message = ProviderErrors.AZURE_MISSING_STORAGE_ACCOUNT_MESSAGE
            raise ValidationError(error_obj(key, message))

        if subscription_id and storage_account and not resource_group:
            key = ProviderErrors.AZURE_MISSING_PATCH
            message = ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_MESSAGE
            raise ValidationError(error_obj(key, message))

        if storage_account and resource_group and not subscription_id:
            key = ProviderErrors.AZURE_MISSING_PATCH
            message = ProviderErrors.AZURE_MISSING_SUBSCRIPTION_ID_MESSAGE
            raise ValidationError(error_obj(key, message))

        if not resource_group and not storage_account and not subscription_id:
            key = ProviderErrors.AZURE_MISSING_PATCH
            message = ProviderErrors.AZURE_MISSING_ALL_PATCH_VALUES_MESSAGE
            raise ValidationError(error_obj(key, message))

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
        key = "azure.error"

        azure_service = None

        if not (isinstance(credential_name, dict) and isinstance(storage_resource_name, dict)):
            message = "Resource group and/or Storage account must be a dict"
            raise ValidationError(error_obj(key, message))

        resource_group = storage_resource_name.get("resource_group")
        storage_account = storage_resource_name.get("storage_account")
        subscription_id = credential_name.get("subscription_id")

        self._verify_patch_entries(subscription_id, resource_group, storage_account)

        try:
            azure_service = AzureService(
                **credential_name, resource_group_name=resource_group, storage_account_name=storage_account
            )
            azure_client = AzureClientFactory(**credential_name)
            storage_accounts = azure_client.storage_client.storage_accounts
            storage_account = storage_accounts.get_properties(resource_group, storage_account)
            if azure_service and not azure_service.describe_cost_management_exports():
                key = ProviderErrors.AZURE_NO_REPORT_FOUND
                message = ProviderErrors.AZURE_MISSING_EXPORT_MESSAGE
                raise ValidationError(error_obj(key, message))
        except AzureCostReportNotFound as costreport_err:
            key = ProviderErrors.AZURE_BILLING_SOURCE_NOT_FOUND
            raise ValidationError(error_obj(key, str(costreport_err)))
        except (AdalError, AzureException, AzureServiceError, ClientException, TypeError) as exc:
            key = ProviderErrors.AZURE_CLIENT_ERROR
            raise ValidationError(error_obj(key, str(exc)))

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
