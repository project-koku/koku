#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Defines the Ingress Access Permissions class."""
from django.conf import settings

from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.provider.models import Provider

ACCESS_TYPE_MAP = {
    Provider.PROVIDER_AWS: AwsAccessPermission.resource_type,
    Provider.PROVIDER_AWS_LOCAL: AwsAccessPermission.resource_type,
    Provider.PROVIDER_AZURE: AzureAccessPermission.resource_type,
    Provider.PROVIDER_AZURE_LOCAL: AzureAccessPermission.resource_type,
    Provider.PROVIDER_GCP: GcpAccessPermission.resource_type,
    Provider.PROVIDER_GCP_LOCAL: GcpAccessPermission.resource_type,
    Provider.PROVIDER_OCP: OpenShiftAccessPermission.resource_type,
}
ACCESS_RESOURCE_TYPES = tuple(ACCESS_TYPE_MAP.values())


class IngressAccessPermission:
    """Utility class for Ingress RBAC checks."""

    @staticmethod
    def has_access(request, provider_type, write=False):
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True
        access = getattr(request.user, "access", None)
        if not access or not isinstance(access, dict):
            return False
        resource_type = ACCESS_TYPE_MAP.get(provider_type)
        if not resource_type:
            return False
        resource_access = access.get(resource_type, {})
        if write:
            write_access = resource_access.get("write", [])
            return bool(write_access)
        return bool(resource_access.get("read", []))

    @staticmethod
    def has_any_read_access(request):
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True
        access = getattr(request.user, "access", None)
        if not access or not isinstance(access, dict):
            return False
        for resource_type in ACCESS_RESOURCE_TYPES:
            if access.get(resource_type, {}).get("read", []):
                return True
        return False
