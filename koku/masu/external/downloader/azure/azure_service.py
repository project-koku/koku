import os
from datetime import datetime, timedelta
from isodate import datetime_isoformat
from dateutil.relativedelta import relativedelta
from tempfile import NamedTemporaryFile
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    Export,
    ExportDeliveryInfo,
    ExportDeliveryDestination,
    ExportRecurrencePeriod,
    ExportSchedule,
    QueryDataset,
    QueryDefinition)
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.scheduler.models import JobCollectionDefinition, JobCollectionProperties, Sku
from azure.mgmt.storage.models import StorageAccountCreateParameters
from azure.mgmt.storage.models import (
    Kind,
    Sku,
    SkuName,
    StorageAccountCreateParameters,
    StorageAccountUpdateParameters
)
from azure.storage import CloudStorageAccount
from azure.storage.blob import BlockBlobService
from msrestazure.azure_exceptions import CloudError


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

    def _get_resource_client(self):
        """Get resource client with subscription and credentials."""
        return ResourceManagementClient(self.credentials, self.subscription_id)

    def _get_storage_client(self):
        """Get storage client with subscription and credentials."""
        return StorageManagementClient(self.credentials, self.subscription_id)

    def _get_cost_management_client(self):
        """Get cost management client with subscription and credentials."""
        return CostManagementClient(self.credentials, self.subscription_id)

    def create_resource_group(self, resource_group_name, region):
        """Create resource group."""
        resource_client = self._get_resource_client()
        resource_group_params = {'location': region}
        return resource_client.resource_groups.create_or_update(
            resource_group_name, resource_group_params)
        
    def delete_resource_group(self, resource_group_name):
        """Delete resource group."""
        resource_client = self._get_resource_client()
        try:
            delete_async_operation = resource_client.resource_groups.delete(
                resource_group_name)
            delete_async_operation.wait()
        except CloudError as cloud_error:
            raise AzureResourceGroupNotFound(cloud_error.message)

    def create_storage_account(self, resource_group_name, storage_account_name, region):
        """Create storage account in a resource group."""
        
        storage_client = self._get_storage_client()
        availability = storage_client.storage_accounts.check_name_availability(
            storage_account_name)
        if not availability.name_available:
            raise AzureStorageAccountUnavailable(
                f'{availability.reason}: {availability.message}')
        storage_async_operation = storage_client.storage_accounts.create(
            resource_group_name,
            storage_account_name,
            StorageAccountCreateParameters(
                sku=Sku(name=SkuName.standard_ragrs),
                kind=Kind.storage,
                location=region
            )
        )
        storage_account = storage_async_operation.result()
        return storage_account

    def get_storage_account(self, resource_group_name, storage_account_name):
        """Get the Storage Account object in a resource group."""
        storage_client = self._get_storage_client()
        return storage_client.storage_accounts.get_properties(
            resource_group_name, storage_account_name)

    def get_storage_account_keys(self, resource_group_name, storage_account_name):
        """Get the access keys assiociated with a storage account in a resource group."""
        storage_client = self._get_storage_client()
        return storage_client.storage_accounts.list_keys(resource_group_name, storage_account_name)

    def delete_storage_account(self, resource_group_name, storage_account_name):
        """Delete a storage account in a resource group."""
        storage_client = self._get_storage_client()
        storage_client.storage_accounts.delete(
            resource_group_name, storage_account_name)

    def create_storage_account_container(self,
                                         resource_group_name,
                                         storage_account_name,
                                         container_name):
        """Create a storage account container in a resource group."""
        storage_client = self._get_storage_client()
        return storage_client.blob_containers.create(resource_group_name,
                                                     storage_account_name,
                                                     container_name)

    def get_storage_account_container(self,
        resource_group_name,
        storage_account_name,
        container_name):
        """Get the container associated with a storage account."""
        storage_client = self._get_storage_client()
        return storage_client.blob_containers.get(resource_group_name,
                                           storage_account_name,
                                           container_name)

    def _get_cloud_storage_account(self,
                                   resource_group_name,
                                   storage_account_name,
                                   container_name):
        """Get the cloud storage account object."""
        storage_client = self._get_storage_client()
        storage_account_keys = storage_client.storage_accounts.list_keys(
            resource_group_name, storage_account_name)
        # Add check for keys and a get value
        key = storage_account_keys.keys[0]
        return CloudStorageAccount(
            storage_account_name, key.value)

    def list_storage_account_container_blobs(self,
                                             resource_group_name,
                                             storage_account_name,
                                             container_name):
        """List the blobs in a storage account container."""
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name,
                                                                storage_account_name,
                                                                container_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        return blockblob_service.list_blobs(container_name)

    def get_latest_cost_export(self,
                               resource_group_name,
                               storage_account_name,
                               container_name,
                               export_name):
        """Get the latest cost export file from given storage account container."""
        latest_report = None
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name,
                                                                storage_account_name,
                                                                container_name)
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

    def get_cost_export_for_date(self,
                                 billing_period,
                                 resource_group_name,
                                 storage_account_name,
                                 container_name,
                                 export_name):
        """Get the latest cost export file from given storage account container."""
        latest_report = None
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name,
                                                                storage_account_name,
                                                                container_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        blob_list = blockblob_service.list_blobs(container_name)
        for blob in blob_list:
            if blob.name.startswith(export_name) and not latest_report:
                latest_report = blob
            elif blob.name.startswith(export_name) and billing_period in blob.name:
                latest_report = blob
        if not latest_report:
            message = f'No cost report with prefix {export_name} found in ' \
            f'storage account {storage_account_name} with container {container_name}.'
            raise AzureCostReportNotFound(message)
        return latest_report

    def get_cost_export_for_key(self,
                                 key,
                                 resource_group_name,
                                 storage_account_name,
                                 container_name,
                                 export_name):
        """Get the latest cost export file from given storage account container."""
        latest_report = None
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name,
                                                                storage_account_name,
                                                                container_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        blob_list = blockblob_service.list_blobs(container_name)
        for blob in blob_list:
            if blob.name.startswith(export_name) and not latest_report:
                latest_report = blob
            elif blob.name.startswith(export_name) and key == blob.name:
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
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name,
                                                                storage_account_name,
                                                                container_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        latest = self.get_latest_cost_export(
            resource_group_name, storage_account_name, container_name, export_name)

        file_path = destination
        if not destination:
            temp_file = NamedTemporaryFile(delete=False, suffix='.csv')
            file_path = temp_file.name
        blockblob_service.get_blob_to_path(container_name, latest.name, file_path)
        return file_path

    def download_cost_export(self,
                             key,
                             resource_group_name,
                             storage_account_name,
                             container_name,
                             export_name,
                             destination=None):
        """Download the latest cost export file from a given storage container."""
        cloud_storage_account = self._get_cloud_storage_account(resource_group_name,
                                                                storage_account_name,
                                                                container_name)
        blockblob_service = cloud_storage_account.create_block_blob_service()
        latest = self.get_cost_export_for_key(
            key, resource_group_name, storage_account_name, container_name, export_name)

        file_path = destination
        if not destination:
            temp_file = NamedTemporaryFile(delete=False, suffix='.csv')
            file_path = temp_file.name
        blockblob_service.get_blob_to_path(container_name, latest.name, file_path)
        return file_path

    def create_cost_management_export(self,
        export_name,
        resource_group_name,
        storage_account_name,
        container_name):
        """Create cost management export."""
        cost_management_client = self._get_cost_management_client()
        storage_account = None
        scope = f'/subscriptions/{self.subscription_id}'
        try:
            storage_account = self.get_storage_account(
                resource_group_name,
                storage_account_name
            )
        except CloudError as cloud_error:
            raise AzureStorageAccountNotFound(f'{cloud_error.message}')
        try:
            self.get_storage_account_container(
                resource_group_name,
                storage_account_name,
                container_name
            )
        except CloudError as cloud_error:
            raise AzureStorageAccountContainerNotFound(
                f'{cloud_error.message}'
            )
        destination = ExportDeliveryDestination(
            resource_id=storage_account.id,
            container=container_name,
            root_folder_path=None)
        delivery_info = ExportDeliveryInfo(destination=destination)
        daily = QueryDataset(granularity='Daily')
        definition = QueryDefinition(timeframe='MonthToDate', dataset=daily)
        report_format = 'Csv'
        from_date = datetime.today() + timedelta(1)
        to_date = datetime.today() + relativedelta(years=5)
        recurrence_period = ExportRecurrencePeriod(
            from_property=datetime_isoformat(from_date),
            to=datetime_isoformat(to_date))
        schedule = ExportSchedule(
            status = 'Active',
            recurrence='Daily',
            recurrence_period=recurrence_period)
        parameters = Export(
            delivery_info=delivery_info,
            definition=definition,
            format=report_format,
            schedule=schedule
        )
        export = cost_management_client.exports.create_or_update(
            scope, export_name, parameters)
        return export

    def list_cost_management_export(self):
        """List cost management export."""
        cost_management_client = self._get_cost_management_client()
        scope = f'/subscriptions/{self.subscription_id}'
        return cost_management_client.exports.list(scope)
