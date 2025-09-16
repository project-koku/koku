#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Client Configuration."""
from azure.identity import ClientSecretCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient

from koku.settings import AZURE_COST_MGMT_CLIENT_API_VERSION


class AzureClientFactory:
    """Azure client factory.

    This class holds the Azure credentials and can create Service Clients for
    querying the Azure Service APIs.

    Args:
        subscription_id (str): Subscription ID
        tenant_id (str): Tenant ID for your Azure Subscription
        client_id (str): Service Principal Application ID
        client_secret (str): Service Principal Password
        cloud (str): Cloud selector, must be one of ['china', 'germany', 'public', 'usgov']
        scope (str): Cost Export scope
        export_name (str): Cost Export name

    """

    def __init__(
        self, subscription_id, tenant_id, client_id, client_secret, cloud="public", scope=None, export_name=None
    ):
        """Constructor."""
        self._subscription_id = subscription_id
        self._scope = scope
        self._export_name = export_name
        self._credentials = ClientSecretCredential(tenant_id, client_id, client_secret)

    @property
    def credentials(self):
        """Service Principal Credentials property."""
        return self._credentials

    @property
    def cost_management_client(self):
        """Get cost management client with subscription and credentials."""
        return CostManagementClient(self.credentials, api_version=AZURE_COST_MGMT_CLIENT_API_VERSION)

    @property
    def storage_client(self):
        """Get storage client with subscription and credentials."""
        return StorageManagementClient(self.credentials, self.subscription_id)

    @property
    def subscription_id(self):
        """Subscription ID property."""
        return self._subscription_id

    def cloud_storage_account(self, storage_account_name):
        """
        Get a BlobServiceClient using RBAC (Role-Based Access Control).
        """
        account_url = f"https://{storage_account_name}.blob.core.windows.net"

        return BlobServiceClient(account_url, credential=self.credentials)

    @property
    def scope(self):
        """Cost Export scope property."""
        return self._scope

    @property
    def export_name(self):
        """Cost Export name."""
        return self._export_name
