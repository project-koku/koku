#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider error constants."""


class SkipStatusPush(Exception):
    """Raise when platform source status should be skipped."""


class ProviderErrors:
    """Error keys for provider account checks."""

    # KEYS
    INVALID_SOURCE_TYPE = "source_type"
    DUPLICATE_AUTH = "source.duplicate"
    BILLING_SOURCE = "billing_source"

    AWS_NO_REPORT_FOUND = "authentication.role_arn.noreportfound"
    AWS_REPORT_CONFIG = "aws.report.configuration"
    AWS_COMPRESSION_REPORT_CONFIG = "aws.report.compression.configuration"
    AWS_MISSING_ROLE_ARN = "authentication.role_arn.missing"
    AWS_ROLE_ARN_UNREACHABLE = "authentication.role_arn.unreachable"
    AWS_BUCKET_MISSING = "billing_source.bucket.missing"
    AWS_BILLING_SOURCE_NOT_FOUND = "billing_source.bucket.notfound"
    AWS_REPORT_NOT_FOUND = "report.notfound"

    AZURE_MISSING_PATCH = "azure.missing.patch"
    AZURE_MISSING_DATA_SOURCE = "billing_source.data_source.missing"
    AZURE_NO_REPORT_FOUND = "authentication.credential.noreportfound"
    AZURE_BILLING_SOURCE_NOT_FOUND = "billing_source.data_source.notfound"
    AZURE_CREDENTAL_UNREACHABLE = "authentication.credentials.unreachable"
    AZURE_CLIENT_ERROR = "azure.exception"
    AZURE_REPORT_NOT_FOUND = "report.notfound"

    GCP_INCORRECT_IAM_PERMISSIONS = "gcp.iam.permissions"
    GCP_BUCKET_MISSING = "gcp.billing_source.bucket.missing"
    GCP_REPORT_NOT_FOUND = "billing_source.bucket.noreportfound"

    OCI_NO_REPORT_FOUND = "billing_source.bucket.noreportfound"
    OCI_REGION_NOT_SUPPORTED = "billing_source.bucket_region.notsupported"
    OCI_BUCKET_MISSING = "billing_source.bucket.missing"
    OCI_BUCKET_NAMESPACE_MISSING = "billing_source.bucket_namespace.missing"
    OCI_BUCKET_REGION_MISSING = "billing_source.bucket_region.missing"

    # MESSAGES
    INVALID_SOURCE_TYPE_MESSAGE = "The given source type is not supported."
    BILLING_SOURCE_GENERAL_ERROR = "There is a problem with the given source."
    REQUIRED_FIELD_MISSING = "The source is missing one or more required fields."

    AWS_MISSING_ROLE_ARN_MESSAGE = "Role ARN is a required parameter for AWS and must not be blank."
    AWS_ROLE_ARN_UNREACHABLE_MESSAGE = (
        "The role ARN was entered incorrectly for this source. "
        "Edit your AWS source and verify the name of your ARN."
    )
    AWS_BUCKET_MISSING_MESSAGE = (
        "Cost management requires an S3 bucket to store cost and usage reports. "
        "Edit your AWS source to include the name of your S3 bucket."
    )
    AWS_BILLING_SOURCE_NOT_FOUND_MESSAGE = (
        "The S3 bucket was entered incorrectly for this source. "
        "Edit your AWS source and verify the name of your S3 bucket."
    )
    AWS_COMPRESSION_REPORT_CONFIG_MESSAGE = (
        "Cost management requires that AWS Cost and Usage Reports use GZIP compression format."
    )
    AZURE_MISSING_EXPORT_MESSAGE = (
        "The Azure cost export cannot be found. Ensure the Storage account name, Resource group name, "
        "and Subscription ID are correct. In Azure, create a daily export task for your storage account."
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
        "Cost management requires a subscription ID or scope with"
        " export name for this source. "
        "Edit your Azure source to include the subscription ID."
    )
    AZURE_MISSING_EXPORT_NAME_MESSAGE = (
        "Cost management requires an export name when a scope is"
        " provided for a source. "
        "Edit your Azure source to include an export name."
    )
    AZURE_MISSING_ALL_PATCH_VALUES_MESSAGE = (
        "Cost management requires a resource group,  storage account"
        " and subscription ID or scope with export name. "
        "Edit your Azure source to include these details."
    )
    AZURE_EXPIRED_CLIENT_SECRET_KEYS_MESSAGE = (
        "The provided client secret keys for this source are expired. "
        "In Azure, refresh your client secret and try again."
    )
    AZURE_INCORRECT_CLIENT_SECRET_MESSAGE = (
        "A problem has been detected with the Azure client secret for this source. "
        "Refer to the Microsoft Azure troubleshooting guide in the cost management documentation for details."
    )
    AZURE_INCORRECT_CLIENT_ID_MESSAGE = (
        "The client ID was entered incorrectly for this source. Edit your Azure source and verify the client ID."
    )
    AZURE_INCORRECT_TENANT_ID_MESSAGE = (
        "The tenant ID was entered incorrectly for this source. Edit your Azure source and verify the tenant ID."
    )
    AZURE_INCORRECT_RESOURCE_GROUP_MESSAGE = (
        "The resource group was entered incorrectly for this source. "
        "Edit your Azure source and verify the resource group."
    )
    AZURE_INCORRECT_STORAGE_ACCOUNT_MESSAGE = (
        "The storage account was entered incorrectly for this source. "
        "Edit your Azure source and verify the storage account."
    )
    AZURE_INCORRECT_SUBSCRIPTION_ID_MESSAGE = (
        "The subscription ID was entered incorrectly for this source. "
        "Edit your Azure source and verify the subscription ID."
    )
    AZURE_UNAUTHORIZED_MESSAGE = (
        "Azure reported an authorization error. "
        "In Azure, check the resource group, storage account, cost export scope, and service principal."
    )
    AZURE_GENERAL_CLIENT_ERROR_MESSAGE = "Azure client configuration error."
    OCI_BUCKET_MISSING_MESSAGE = (
        "Cost management requires an OCI bucket to store cost and usage reports. "
        "Edit your OCI source to include the name of your OCI bucket."
    )
    OCI_BUCKET_NAMESPACE_MISSING_MESSAGE = (
        "Cost management requires the namespace for the OCI bucket storing cost and usage reports. "
        "Edit your OCI source to include the namespace of your OCI bucket."
    )
    OCI_BUCKET_REGION_MISSING_MESSAGE = (
        "Cost management requires the region for the OCI bucket storing cost and usage reports. "
        "Edit your OCI source to include the region of your OCI bucket."
    )
