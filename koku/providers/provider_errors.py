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
    INVALID_SOURCE_TYPE = "source_type"
    DUPLICATE_AUTH = "source.duplicate"

    AWS_NO_REPORT_FOUND = "authentication.provider_resource_name.noreportfound"
    AWS_REPORT_CONFIG = "aws.report.configuration"
    AWS_COMPRESSION_REPORT_CONFIG = "aws.report.compression.configuration"
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
    INVALID_SOURCE_TYPE_MESSAGE = "The given source type is not supported."

    AWS_MISSING_RESOURCE_NAME_MESSAGE = "Provider resource name is a required parameter for AWS and must not be blank."
    AWS_RESOURCE_NAME_UNREACHABLE_MESSAGE = (
        "The role ARN has been entered incorrectly for this source. "
        "Edit your AWS source and verify the name of your ARN."
    )
    AWS_BUCKET_MISSING_MESSAGE = (
        "Cost management requires an S3 bucket to store cost and usage reports. "
        "Edit your AWS source to include the name of your S3 bucket."
    )
    AWS_BILLING_SOURCE_NOT_FOUND_MESSAGE = (
        "The S3 bucket has been entered incorrectly for this source. "
        "Edit your AWS source and verify the name of your S3 bucket."
    )
    AWS_COMPRESSION_REPORT_CONFIG_MESSAGE = (
        "Cost management requires that AWS Cost and Usage Reports use GZIP compression format."
    )
    AZURE_MISSING_EXPORT_MESSAGE = (
        "A cost management export cannot be found. In Azure, create a daily export task for your storage account."
    )
    AZURE_MISSING_RESOURCE_GROUP_AND_STORAGE_ACCOUNT_MESSAGE = (
        "Cost management requires a resource group and "
        "storage account for this source. Edit your Azure "
        "source to include these details."
    )
    AZURE_MISSING_STORAGE_ACCOUNT_MESSAGE = (
        "Cost management requires a storage account for this source. "
        "Edit your Azure source to include the storage account."
    )
    AZURE_MISSING_RESOURCE_GROUP_MESSAGE = (
        "Cost management requires a resource group for this source. "
        "Edit your Azure source to include the resource group."
    )
    AZURE_MISSING_SUBSCRIPTION_ID_MESSAGE = (
        "Cost management requires a subscription ID for this source. "
        "Edit your Azure source to include the subscription ID."
    )
    AZURE_MISSING_ALL_PATCH_VALUES_MESSAGE = (
        "Cost management requires more information for your Azure source. "
        "Edit your Azure source to include the subscription ID, resource group "
        "and storage account."
    )
    AZURE_INCORRECT_CLIENT_SECRET_MESSAGE = (
        "The client secret has been entered incorrectly for this source. "
        "Edit your Azure source and verify the client secret."
    )
    AZURE_INCORRECT_CLIENT_ID_MESSAGE = (
        "The client ID has been entered incorrectly for this source. "
        "Edit your Azure source and verify the client ID."
    )
    AZURE_INCORRECT_RESOURCE_GROUP_MESSAGE = (
        "The resource group has been entered incorrectly for this source. "
        "Edit your Azure source and verify the resource group."
    )
    AZURE_INCORRECT_STORAGE_ACCOUNT_MESSAGE = (
        "The storage account has been entered incorrectly for this source. "
        "Edit your Azure source and verify the storage account."
    )
    AZURE_INCORRECT_SUBSCRIPTION_ID_MESSAGE = (
        "The subscription ID has been entered incorrectly for this source. "
        "Edit your Azure source and verify the subscription ID."
    )
    AZURE_GENERAL_CLIENT_ERROR_MESSAGE = "Azure client configuration error."
