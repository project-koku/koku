#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCP-on-Azure tags."""
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.tags.azure.openshift.queries import OCPAzureTagQueryHandler
from api.tags.azure.openshift.serializers import OCPAzureTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.azure.models import AzureEnabledTagKeys


class OCPAzureTagView(TagView):
    """Get OpenShift-on-Azure tags."""

    provider = "ocp_azure"
    serializer = OCPAzureTagsQueryParamSerializer
    query_handler = OCPAzureTagQueryHandler
    tag_handler = [AzureEnabledTagKeys]
    permission_classes = [AzureAccessPermission & OpenShiftAccessPermission]
