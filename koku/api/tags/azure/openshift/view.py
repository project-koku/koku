#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCP-on-Azure tags."""
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.provider.models import Provider
from api.tags.azure.openshift.queries import OCPAzureTagQueryHandler
from api.tags.azure.openshift.serializers import OCPAzureTagsQueryParamSerializer
from api.tags.view import TagView


class OCPAzureTagView(TagView):
    """Get OpenShift-on-Azure tags."""

    provider = "ocp_azure"
    serializer = OCPAzureTagsQueryParamSerializer
    query_handler = OCPAzureTagQueryHandler
    tag_providers = [Provider.PROVIDER_AZURE, Provider.PROVIDER_OCP]
    permission_classes = [AzureAccessPermission & OpenShiftAccessPermission]
