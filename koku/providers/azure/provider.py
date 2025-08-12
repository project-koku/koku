#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure provider."""
from azure.common import AzureException
from azure.core.exceptions import AzureError
from azure.core.exceptions import ClientAuthenticationError
from azure.core.exceptions import HttpResponseError
from azure.core.exceptions import ServiceRequestError
from rest_framework import serializers
from rest_framework.serializers import ValidationError

from ..provider_errors import ProviderErrors
from ..provider_interface import ProviderInterface
from .client import AzureClientFactory
from api.common import error_obj
from api.models import Provider
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.azure.azure_service import AzureService
from masu.external.downloader.azure.azure_service import AzureServiceError


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

    def _verify_patch_entries(self, subscription_id, resource_group, storage_account, scope, export_name):
        """Raise Validation Error for missing."""
        key = ProviderErrors.AZURE_MISSING_PATCH
        if scope and not export_name:
            message = ProviderErrors.AZURE_MISSING_EXPORT_NAME_MESSAGE
            raise ValidationError(error_obj(key, message))

        if subscription_id or scope:
            if not resource_group and not storage_account:
                message = ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_AND_STORAGE_ACCOUNT_MESSAGE
                raise ValidationError(error_obj(key, message))

            elif resource_group and not storage_account:
                message = ProviderErrors.AZURE_MISSING_STORAGE_ACCOUNT_MESSAGE
                raise ValidationError(error_obj(key, message))

            elif not resource_group:
                message = ProviderErrors.AZURE_MISSING_RESOURCE_GROUP_MESSAGE
                raise ValidationError(error_obj(key, message))

        if storage_account and resource_group and not subscription_id and not scope:
            message = ProviderErrors.AZURE_MISSING_SUBSCRIPTION_ID_MESSAGE
            raise ValidationError(error_obj(key, message))

        if not resource_group and not storage_account and not subscription_id and not scope:
            message = ProviderErrors.AZURE_MISSING_ALL_PATCH_VALUES_MESSAGE
            raise ValidationError(error_obj(key, message))

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

        azure_service = None

        if not (isinstance(credentials, dict) and isinstance(data_source, dict)):
            message = "Resource group and/or Storage account must be a dict"
            raise ValidationError(error_obj(key, message))

        resource_group = data_source.get("resource_group")
        storage_account = data_source.get("storage_account")
        scope = data_source.get("scope")
        export_name = data_source.get("export_name")
        subscription_id = credentials.get("subscription_id")

        self._verify_patch_entries(subscription_id, resource_group, storage_account, scope, export_name)

        storage_only = data_source.get("storage_only")
        if storage_only:
            # Limited storage access
            return True

        try:
            azure_service = AzureService(
                **credentials,
                resource_group_name=resource_group,
                storage_account_name=storage_account,
                scope=scope,
                export_name=export_name,
            )
            azure_client = AzureClientFactory(**credentials)
            storage_accounts = azure_client.storage_client.storage_accounts
            storage_account = storage_accounts.get_properties(resource_group, storage_account)
            if azure_service and not azure_service.describe_cost_management_exports():
                key = ProviderErrors.AZURE_NO_REPORT_FOUND
                message = ProviderErrors.AZURE_MISSING_EXPORT_MESSAGE
                raise ValidationError(error_obj(key, message))
        except AzureCostReportNotFound as costreport_err:
            key = ProviderErrors.AZURE_BILLING_SOURCE_NOT_FOUND
            raise ValidationError(error_obj(key, str(costreport_err)))
        except (
            ClientAuthenticationError,
            ServiceRequestError,
            AzureError,
            AzureException,
            AzureServiceError,
            HttpResponseError,
            TypeError,
            ValueError,
        ) as exc:
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

    def is_file_reachable(self, source, reports_list):
        """Verify that report files are accessible in Azure."""
        resource_group = source.billing_source.data_source.get("resource_group")
        storage_account = source.billing_source.data_source.get("storage_account")
        subscription_id = source.authentication.credentials.get("subscription_id")
        tenant_id = source.authentication.credentials.get("tenant_id")
        client_id = source.authentication.credentials.get("client_id")
        client_secret = source.authentication.credentials.get("client_secret")
        try:
            azure_client = AzureClientFactory(subscription_id, tenant_id, client_id, client_secret)
            storage_client = azure_client.cloud_storage_account(resource_group, storage_account)
            for report in reports_list:
                container_name = report.split("/")[0]
                report_key = report.split(f"{container_name}/")[-1]
                blob_client = storage_client.get_blob_client(container_name, report_key)
                if not blob_client.exists():
                    internal_message = f"File {report_key} could not be found within container {container_name}."
                    key = ProviderErrors.AZURE_REPORT_NOT_FOUND
                    raise serializers.ValidationError(error_obj(key, internal_message))
        except (
            ClientAuthenticationError,
            ServiceRequestError,
            AzureError,
            AzureException,
            AzureServiceError,
            HttpResponseError,
            TypeError,
            ValueError,
        ) as exc:
            key = ProviderErrors.AZURE_CLIENT_ERROR
            raise ValidationError(error_obj(key, str(exc)))
