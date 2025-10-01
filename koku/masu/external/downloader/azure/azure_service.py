#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Service helpers."""
import logging
from tempfile import NamedTemporaryFile

from azure.common import AzureException
from azure.core.exceptions import AzureError
from azure.core.exceptions import ClientAuthenticationError
from azure.core.exceptions import HttpResponseError
from azure.core.exceptions import ResourceNotFoundError
from azure.core.exceptions import ServiceRequestError
from azure.storage.blob._models import BlobProperties

from masu.util.azure.common import AzureBlobExtension
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
        scope=None,
        export_name=None,
    ):
        """Establish connection information."""
        self._resource_group_name = resource_group_name
        self._storage_account_name = storage_account_name
        self._factory = AzureClientFactory(
            subscription_id, tenant_id, client_id, client_secret, cloud, scope, export_name
        )

        if not self._factory.subscription_id:
            raise AzureServiceError("Azure Service missing subscription id.")

        self._blob_service_client = self._factory.blob_service_client(resource_group_name, storage_account_name)

        if not self._factory.credentials:
            raise AzureServiceError("Azure Service credentials are not configured.")

    def _get_latest_blob(
        self, report_path: str, blobs: list[BlobProperties], extension: str | None = None
    ) -> BlobProperties | None:
        latest_blob = None
        for blob in blobs:
            if extension and not blob.name.endswith(extension):
                continue
            if report_path in blob.name:
                if not latest_blob or blob.last_modified > latest_blob.last_modified:
                    latest_blob = blob
        return latest_blob

    def _get_latest_blob_for_path(
        self,
        report_path: str,
        container_name: str,
        extension: str | None = None,
    ) -> BlobProperties:
        """Get the latest file with the specified extension from given storage account container."""

        latest_file = None
        if not container_name:
            message = "Unable to gather latest file as container name is not provided."
            LOG.warning(message)
            raise AzureCostReportNotFound(message)

        try:
            container_client = self._blob_service_client.get_container_client(container_name)
            blobs = list(container_client.list_blobs(name_starts_with=report_path))
        except (ClientAuthenticationError, ServiceRequestError, AzureException) as error:
            raise AzureServiceError("Failed to download file. Error: ", str(error))
        except ResourceNotFoundError as Error:
            message = f"Specified container {container_name} does not exist for report path {report_path}."
            error_msg = f"{message} Azure Error: {Error}."
            LOG.warning(error_msg)
            raise AzureCostReportNotFound(message)
        except HttpResponseError as httpError:
            if httpError.status_code == 403:
                message = (
                    "An authorization error occurred attempting to gather latest file"
                    f" in container {container_name} for "
                    f"path {report_path}."
                )
            else:
                message = (
                    "Unknown error occurred attempting to gather latest file"
                    f" in container {container_name} for "
                    f"path {report_path}."
                )
            error_msg = f"{message} Azure Error: {httpError}."
            LOG.warning(error_msg)
            raise AzureCostReportNotFound(message)

        latest_file = self._get_latest_blob(report_path, blobs, extension)
        if not latest_file:
            message = f"No file found in container " f"'{container_name}' for path '{report_path}'."
            raise AzureCostReportNotFound(message)

        return latest_file

    def _list_blobs(self, starts_with: str, container_name: str) -> list[BlobProperties]:
        try:
            container_client = self._blob_service_client.get_container_client(container_name)
            blob_names = list(container_client.list_blobs(name_starts_with=starts_with))
        except (
            ClientAuthenticationError,
            ServiceRequestError,
            AzureException,
            ResourceNotFoundError,
        ) as ex:
            raise AzureServiceError(f"Unable to list blobs. Error: {ex}")

        if not blob_names:
            raise AzureCostReportNotFound(
                f"Unable to find files in container '{container_name}' at path '{starts_with}'"
            )

        return blob_names

    def get_file_for_key(self, key: str, container_name: str) -> BlobProperties:
        """Get the file from given storage account container."""

        blob_list = self._list_blobs(key, container_name)
        report = None
        for blob in blob_list:
            if key == blob.name:
                report = blob
                break

        if not report:
            message = f"No file for report name {key} found in container {container_name}."
            raise AzureCostReportNotFound(message)

        return report

    def get_latest_cost_export_for_path(self, report_path: str, container_name: str) -> BlobProperties:
        """
        Get the latest cost export for a given path and container based on the compression type.

        Args:
            report_path (str): The path where the report is stored.
            container_name (str): The name of the container where the report is located.
            compression (str): The compression format ('gzip' or 'csv').

        Returns:
            BlobProperties: The latest blob corresponding to the specified report path and container.

        Raises:
            ValueError: If the compression type is not 'gzip' or 'csv'.
            AzureCostReportNotFound: If no blob is found for the given path and container.
        """
        return self._get_latest_blob_for_path(report_path, container_name)

    def get_latest_manifest_for_path(self, report_path: str, container_name: str) -> BlobProperties:
        return self._get_latest_blob_for_path(report_path, container_name, AzureBlobExtension.json.value)

    def download_file(
        self,
        key: str,
        container_name: str,
        destination: str = None,
        suffix: str = AzureBlobExtension.csv.value,
        ingress_reports: list[str] = None,
    ) -> str:
        """
        Download the file from a given storage container. Supports both CSV and GZIP formats.
        """

        if not ingress_reports:
            cost_export = self.get_file_for_key(key, container_name)
            key = cost_export.name

        file_path = destination
        if not destination:
            temp_file = NamedTemporaryFile(delete=False, suffix=suffix)
            temp_file.close()
            file_path = temp_file.name

        try:
            blob_client = self._blob_service_client.get_blob_client(container_name, key)
            with open(file_path, "wb") as blob_download:
                blob_download.write(blob_client.download_blob().readall())
        except (
            ClientAuthenticationError,
            ServiceRequestError,
            AzureException,
            OSError,
            AzureError,
        ) as error:
            raise AzureServiceError("Failed to download cost export. Error: ", str(error))

        return file_path

    def describe_cost_management_exports(self):
        """List cost management export."""
        export_reports = []
        scope = self._factory.scope
        export_name = self._factory.export_name
        if not scope:
            scope = f"/subscriptions/{self._factory.subscription_id}"

        if export_name:
            try:
                cost_management_client = self._factory.cost_management_client
                report = cost_management_client.exports.get(scope, export_name)
                report_def = {
                    "name": report.name,
                    "container": report.delivery_info.destination.container,
                    "directory": report.delivery_info.destination.root_folder_path,
                }
                export_reports.append(report_def)
            except (ClientAuthenticationError, ServiceRequestError, AzureException) as exc:
                raise AzureCostReportNotFound(exc)

            return export_reports

        expected_resource_id = (
            f"/subscriptions/{self._factory.subscription_id}/resourceGroups/"
            f"{self._resource_group_name}/providers/Microsoft.Storage/"
            f"storageAccounts/{self._storage_account_name}"
        )
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
        except (ClientAuthenticationError, ServiceRequestError, AzureException) as exc:
            raise AzureCostReportNotFound(exc)

        return export_reports
