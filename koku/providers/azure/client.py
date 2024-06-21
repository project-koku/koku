#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Client Configuration."""
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from msrestazure.azure_cloud import AZURE_CHINA_CLOUD
from msrestazure.azure_cloud import AZURE_GERMAN_CLOUD
from msrestazure.azure_cloud import AZURE_PUBLIC_CLOUD
from msrestazure.azure_cloud import AZURE_US_GOV_CLOUD

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

        clouds = {
            "china": AZURE_CHINA_CLOUD,
            "germany": AZURE_GERMAN_CLOUD,
            "public": AZURE_PUBLIC_CLOUD,
            "usgov": AZURE_US_GOV_CLOUD,
        }

        self._credentials = ClientSecretCredential(
            tenant_id, client_id, client_secret, cloud_environment=clouds.get(cloud, "public")
        )

    @property
    def credentials(self):
        """Service Principal Credentials property."""
        return self._credentials

    @property
    def cost_management_client(self):
        """Get cost management client with subscription and credentials."""
        return CostManagementClient(self.credentials, api_version=AZURE_COST_MGMT_CLIENT_API_VERSION)

    @property
    def resource_client(self):
        """Return a resource client."""
        return ResourceManagementClient(self.credentials, self.subscription_id)

    @property
    def storage_client(self):
        """Get storage client with subscription and credentials."""
        return StorageManagementClient(self.credentials, self.subscription_id)

    @property
    def compute_client(self):
        """Get compute client with subscription and credentials."""
        return ComputeManagementClient(self.credentials, self.subscription_id)

    @property
    def subscription_id(self):
        """Subscription ID property."""
        return self._subscription_id

    def cloud_storage_account(self, resource_group_name, storage_account_name):
        """Get a BlobServiceClient."""
        storage_account_keys = self.storage_client.storage_accounts.list_keys(
            resource_group_name, storage_account_name
        )
        # Add check for keys and a get value
        key = storage_account_keys.keys[0]

        connect_str = (
            f"DefaultEndpointsProtocol=https;"
            f"AccountName={storage_account_name};"
            f"AccountKey={key.value};"
            f"EndpointSuffix=core.windows.net"
        )
        return BlobServiceClient.from_connection_string(connect_str)

    @property
    def scope(self):
        """Cost Export scope property."""
        return self._scope

    @property
    def export_name(self):
        """Cost Export name."""
        return self._export_name
