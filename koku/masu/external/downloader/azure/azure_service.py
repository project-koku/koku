#
# Copyright 2019 Red Hat, Inc.
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
"""Azure Service helpers."""

import os
from tempfile import NamedTemporaryFile
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage import CloudStorageAccount


class AzureResourceGroupNotFound(Exception):
   """Raised when Azure resource group is not found."""
   pass


class AzureStorageAccountUnavailable(Exception):
   """Raised when Azure storage account is not available."""
   pass


class AzureStorageAccountNotFound(Exception):
   """Raised when Azure storage account is not found."""
   pass


class AzureStorageAccountContainerNotFound(Exception):
   """Raised when Azure storage account container is not found."""
   pass


class AzureCostReportNotFound(Exception):
   """Raised when Azure cost report is not found."""
   pass

class AzureService:
    """A class to handle interactions with the Azure services."""

    def __init__(self):
        """Establish connection information."""
        self.subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        self.client_id = os.environ.get('AZURE_CLIENT_ID')
        self.client_secret = os.environ.get('AZURE_CLIENT_SECRET')
        self.tenant_id = os.environ.get('AZURE_TENANT_ID')
        self.username = os.environ.get('AZURE_USERNAME')
        self.password = os.environ.get('AZURE_PASSWORD')
        if (self.subscription_id and self.client_id and
            self.client_secret and self.tenant_id):
            self.credentials = ServicePrincipalCredentials(
                client_id=self.client_id,
                secret=self.client_secret,
                tenant=self.tenant_id
            )
        else:
            raise ValueError('Azure Service credentials are not configured.')

    def _get_cost_management_client(self):
        """Get cost management client with subscription and credentials."""
        return CostManagementClient(self.credentials, self.subscription_id)

    def _get_storage_client(self):
        """Get storage client with subscription and credentials."""
        return StorageManagementClient(self.credentials, self.subscription_id)

    def _get_cloud_storage_account(self, resource_group_name, storage_account_name):
        """Get the cloud storage account object."""
        storage_client = self._get_storage_client()
        storage_account_keys = storage_client.storage_accounts.list_keys(
            resource_group_name, storage_account_name)
        # Add check for keys and a get value
        key = storage_account_keys.keys[0]
        return CloudStorageAccount(
            storage_account_name, key.value)

    def get_cost_export_for_key(self, key, resource_group_name, storage_account_name, container_name):
        """Get the latest cost export file from given storage account container."""
        report = None
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name, storage_account_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        blob_list = blockblob_service.list_blobs(container_name)
        for blob in blob_list:
            if key == blob.name:
                report = blob
        if not report:
            message = f'No cost report for report name {key} found in ' \
            f'storage account {storage_account_name} with container {container_name}.'
            raise AzureCostReportNotFound(message)
        return report

    def download_cost_export(self, key, resource_group_name, storage_account_name, container_name, destination=None):
        """Download the latest cost export file from a given storage container."""
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name, storage_account_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        latest = self.get_cost_export_for_key(key, resource_group_name, storage_account_name, container_name)

        file_path = destination
        if not destination:
            temp_file = NamedTemporaryFile(delete=False, suffix='.csv')
            file_path = temp_file.name
        blockblob_service.get_blob_to_path(container_name, latest.name, file_path)
        return file_path

    def get_latest_cost_export_for_date(self,
                                        billing_period,
                                        resource_group_name,
                                        storage_account_name,
                                        container_name):
        """Get the latest cost export file from given storage account container."""
        latest_report = None
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name, storage_account_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        blob_list = blockblob_service.list_blobs(container_name)
        for blob in blob_list:
            if billing_period in blob.name and not latest_report:
                latest_report = blob
            elif (billing_period in blob.name and
                  blob.properties.last_modified > latest_report.properties.last_modified):
                latest_report = blob
        if not latest_report:
            message = f'No cost report found in ' \
            f'storage account {storage_account_name} with container {container_name}.'
            raise AzureCostReportNotFound(message)
        return latest_report

    def list_storage_account_container_blobs(self,
                                             resource_group_name,
                                             storage_account_name,
                                             container_name):
        """List the blobs in a storage account container."""
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name, storage_account_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        return blockblob_service.list_blobs(container_name)

    def get_latest_cost_export(self,
                               resource_group_name,
                               storage_account_name,
                               container_name,
                               export_name):
        """Get the latest cost export file from given storage account container."""
        latest_report = None
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name, storage_account_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        blob_list = blockblob_service.list_blobs(container_name)
        for blob in blob_list:
            if blob.name.startswith(export_name) and not latest_report:
                latest_report = blob
            elif (blob.name.startswith(export_name) and
                blob.properties.last_modified > latest_report.properties.last_modified):
                latest_report = blob
        if not latest_report:
            message = f'No cost report with prefix {export_name} found in ' \
            f'storage account {storage_account_name} with container {container_name}.'
            raise AzureCostReportNotFound(message)
        return latest_report

    def download_latest_cost_export(self,
                                    resource_group_name,
                                    storage_account_name,
                                    container_name,
                                    export_name,
                                    destination=None):
        """Download the latest cost export file from a given storage container."""
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name, storage_account_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        latest = self.get_latest_cost_export(
            resource_group_name, storage_account_name, container_name, export_name)

        file_path = destination
        if not destination:
            temp_file = NamedTemporaryFile(delete=False, suffix='.csv')
            file_path = temp_file.name
        blockblob_service.get_blob_to_path(container_name, latest.name, file_path)
        return file_path

    def list_cost_management_export(self):
        """List cost management export."""
        cost_management_client = self._get_cost_management_client()
        scope = f'/subscriptions/{self.subscription_id}'
        return cost_management_client.exports.list(scope)

    def list_containers(self, resource_group_name, storage_account_name):
        """List of containers."""
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name, storage_account_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        container_list = blockblob_service.list_containers()
        found_containers = []
        for container in container_list:
            found_containers.append(container.name)
        return found_containers

    def list_directories(self, container_name, resource_group_name, storage_account_name):
        """List of directories in container."""
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name, storage_account_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        blob_list = blockblob_service.list_blobs(container_name, delimiter='/')
        found_directories = []
        for directory in blob_list:
            found_directories.append(directory.name.strip('/'))
        return found_directories
