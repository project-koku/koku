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
import logging
from tempfile import NamedTemporaryFile

from adal.adal_error import AdalError
from azure.common import AzureException
from azure.core.exceptions import HttpResponseError
from msrest.exceptions import ClientException

from providers.azure.client import AzureClientFactory

LOG = logging.getLogger(__name__)


class AzureServiceError(Exception):
    """Raised when errors are encountered from Azure."""

    pass


class AzureCostReportNotFound(Exception):
    """Raised when Azure cost report is not found."""

    pass


class AzureService:
    """A class to handle interactions with the Azure services."""

    def __init__(
        self,
        tenant_id,
        client_id,
        client_secret,
        resource_group_name,
        storage_account_name,
        subscription_id=None,
        cloud="public",
    ):
        """Establish connection information."""
        self._resource_group_name = resource_group_name
        self._storage_account_name = storage_account_name
        self._factory = AzureClientFactory(subscription_id, tenant_id, client_id, client_secret, cloud)

        if not self._factory.subscription_id:
            raise AzureServiceError("Azure Service missing subscription id.")

        self._cloud_storage_account = self._factory.cloud_storage_account(resource_group_name, storage_account_name)

        if not self._factory.credentials:
            raise AzureServiceError("Azure Service credentials are not configured.")

    def get_cost_export_for_key(self, key, container_name):
        """Get the latest cost export file from given storage account container."""
        report = None
        try:
            container_client = self._cloud_storage_account.get_container_client(container_name)
            blob_list = container_client.list_blobs(name_starts_with=key)
        except (AdalError, AzureException, ClientException) as error:
            raise AzureServiceError("Failed to download cost export. Error: ", str(error))

        for blob in blob_list:
            if key == blob.name:
                report = blob
                break
        if not report:
            message = f"No cost report for report name {key} found in container {container_name}."
            raise AzureCostReportNotFound(message)
        return report

    def download_cost_export(self, key, container_name, destination=None):
        """Download the latest cost export file from a given storage container."""
        cost_export = self.get_cost_export_for_key(key, container_name)

        file_path = destination
        if not destination:
            temp_file = NamedTemporaryFile(delete=False, suffix=".csv")
            file_path = temp_file.name
        try:
            blob_client = self._cloud_storage_account.get_blob_client(container_name, cost_export.name)

            with open(file_path, "wb") as blob_download:
                blob_download.write(blob_client.download_blob().readall())
        except (AdalError, AzureException, ClientException, IOError) as error:
            raise AzureServiceError("Failed to download cost export. Error: ", str(error))
        return file_path

    def get_latest_cost_export_for_path(self, report_path, container_name):
        """Get the latest cost export file from given storage account container."""
        latest_report = None
        if not container_name:
            message = "Unable to gather latest export as container name is not provided."
            LOG.warning(message)
            raise AzureCostReportNotFound(message)

        try:
            container_client = self._cloud_storage_account.get_container_client(container_name)
            blob_list = container_client.list_blobs(name_starts_with=report_path)
            for blob in blob_list:
                if report_path in blob.name and not latest_report:
                    latest_report = blob
                elif report_path in blob.name and blob.last_modified > latest_report.last_modified:
                    latest_report = blob
            if not latest_report:
                message = f"No cost report found in container {container_name} for " f"path {report_path}."
                raise AzureCostReportNotFound(message)
            return latest_report
        except (AdalError, AzureException, ClientException) as error:
            raise AzureServiceError("Failed to download cost export. Error: ", str(error))
        except HttpResponseError as httpError:
            if httpError.status_code == 403:
                message = (
                    "An authorization error occurred attempting to gather latest export"
                    f" in container {container_name} for "
                    f"path {report_path}."
                )
            else:
                message = (
                    "Unknown error occurred attempting to gather latest export"
                    f" in container {container_name} for "
                    f"path {report_path}."
                )
            error_msg = message + f" Azure Error: {httpError}."
            LOG.warning(error_msg)
            raise AzureCostReportNotFound(message)

    def describe_cost_management_exports(self):
        """List cost management export."""
        scope = f"/subscriptions/{self._factory.subscription_id}"
        expected_resource_id = (
            f"/subscriptions/{self._factory.subscription_id}/resourceGroups/"
            f"{self._resource_group_name}/providers/Microsoft.Storage/"
            f"storageAccounts/{self._storage_account_name}"
        )
        export_reports = []
        try:
            cost_management_client = self._factory.cost_management_client
            management_reports = cost_management_client.exports.list(scope)
            for report in management_reports.value:
                if report.delivery_info.destination.resource_id == expected_resource_id:
                    report_def = {
                        "name": report.name,
                        "container": report.delivery_info.destination.container,
                        "directory": report.delivery_info.destination.root_folder_path,
                    }
                    export_reports.append(report_def)
        except (AdalError, AzureException, ClientException) as exc:
            raise AzureCostReportNotFound(exc)

        return export_reports
