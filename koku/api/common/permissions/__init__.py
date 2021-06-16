#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.provider.models import Provider

RESOURCE_TYPES = [
    AwsAccessPermission.resource_type,
    AzureAccessPermission.resource_type,
    OpenShiftAccessPermission.resource_type,
    GcpAccessPermission.resource_type,
]

RESOURCE_TYPE_MAP = {
    AwsAccessPermission.resource_type: [Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL],
    AzureAccessPermission.resource_type: [Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL],
    OpenShiftAccessPermission.resource_type: [Provider.PROVIDER_OCP],
    GcpAccessPermission.resource_type: [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL],
}
