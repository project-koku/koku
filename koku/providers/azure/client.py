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
"""Azure Client Configuration."""

from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage import CloudStorageAccount
from msrestazure.azure_cloud import (AZURE_CHINA_CLOUD,
                                     AZURE_GERMAN_CLOUD,
                                     AZURE_PUBLIC_CLOUD,
                                     AZURE_US_GOV_CLOUD)


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

    """

    # pylint: disable=too-many-arguments
    def __init__(self, subscription_id, tenant_id, client_id, client_secret,
                 cloud='public'):
        """Constructor."""
        self._subscription_id = subscription_id

        clouds = {'china': AZURE_CHINA_CLOUD,
                  'germany': AZURE_GERMAN_CLOUD,
                  'public': AZURE_PUBLIC_CLOUD,
                  'usgov': AZURE_US_GOV_CLOUD}

        self._credentials = ServicePrincipalCredentials(client_id=client_id,
                                                        secret=client_secret,
                                                        tenant=tenant_id,
                                                        cloud_environment=clouds.get(cloud,
                                                                                     'public'))

    @property
    def credentials(self):
        """Service Principal Credentials property."""
        return self._credentials

    @property
    def cost_management_client(self):
        """Get cost management client with subscription and credentials."""
        return CostManagementClient(self.credentials, self.subscription_id)

    @property
    def resource_client(self):
        """Return a resource client."""
        return ResourceManagementClient(self.credentials, self.subscription_id)

    @property
    def storage_client(self):
        """Get storage client with subscription and credentials."""
        return StorageManagementClient(self.credentials, self.subscription_id)

    @property
    def subscription_id(self):
        """Subscription ID property."""
        return self._subscription_id

    def cloud_storage_account(self, resource_group_name, storage_account_name):
        """Get a cloud storage account."""
        storage_account_keys = self.storage_client.storage_accounts.list_keys(
            resource_group_name, storage_account_name)
        # Add check for keys and a get value
        key = storage_account_keys.keys[0]
        return CloudStorageAccount(
            storage_account_name, key.value)
