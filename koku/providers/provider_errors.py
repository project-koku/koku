#
# Copyright 2020 Red Hat, Inc.
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
"""Provider error constants."""


class ProviderErrors:
    """Error keys for provider account checks."""

    # KEYS
    AWS_NO_REPORT_FOUND = "authentication.provider_resource_name.noreportfound"
    AWS_REPORT_CONFIG = "aws.report.configuration"
    AWS_MISSING_RESOURCE_NAME = "authentication.resource_name.missing"
    AWS_RESOURCE_NAME_UNREACHABLE = "authentication.resource_name.unreachable"
    AWS_BUCKET_MISSING = "billing_source.bucket.missing"
    AWS_BILLING_SOURCE_NOT_FOUND = "billing_source.bucket.notfound"

    AZURE_MISSING_PATCH = "azure.missing.patch"
    AZURE_MISSING_DATA_SOURCE = "billing_source.data_source.missing"
    AZURE_NO_REPORT_FOUND = "authentication.credential.noreportfound"
    AZURE_BILLING_SOURCE_NOT_FOUND = "billing_source.data_source.notfound"
    AZURE_CREDENTAL_UNREACHABLE = "authentication.credentials.unreachable"
    AZURE_CLIENT_ERROR = "azure.exception"

    # MESSAGES
    AWS_MISSING_RESOURCE_NAME_MESSAGE = "Provider resource name is a required parameter for AWS and must not be blank."
    AWS_RESOURCE_NAME_UNREACHABLE_MESSAGE = "Incorrect ARN."
    AWS_BUCKET_MISSING_MESSAGE = "Missing S3 bucket."
    AWS_BILLING_SOURCE_NOT_FOUND_MESSAGE = "S3 bucket not found."

    AZURE_MISSING_EXPORT_MESSAGE = "Cost management export was not found."
    AZURE_MISSING_RESOURCE_GROUP_AND_STORAGE_ACCOUNT_MESSAGE = "Missing resource group and storage account."
    AZURE_MISSING_STORAGE_ACCOUNT_MESSAGE = "Missing storage account."
    AZURE_MISSING_RESOURCE_GROUP_MESSAGE = "Missing resource group."
    AZURE_MISSING_SUBSCRIPTION_ID_MESSAGE = "Missing subscription ID."
    AZURE_MISSING_ALL_PATCH_VALUES_MESSAGE = "Missing subscription ID, resource group and storage account."
    AZURE_INCORRECT_CLIENT_SECRET_MESSAGE = "Incorrect Azure client secret"
    AZURE_INCORRECT_CLIENT_ID_MESSAGE = "Incorrect Azure client id."
    AZURE_INCORRECT_RESOURCE_GROUP_MESSAGE = "Incorrect Azure storage resource group."
    AZURE_INCORRECT_STORAGE_ACCOUNT_MESSAGE = "Incorrect Azure storage account."
    AZURE_INCORRECT_SUBSCRIPTION_ID_MESSAGE = "Incorrect Azure subscription id."
    AZURE_GENERAL_CLIENT_ERROR_MESSAGE = "Client configuration error."
