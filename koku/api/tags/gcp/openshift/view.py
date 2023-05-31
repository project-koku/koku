#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCP-on-GCP tags."""
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.provider.models import Provider
from api.tags.gcp.openshift.queries import OCPGCPTagQueryHandler
from api.tags.gcp.openshift.serializers import OCPGCPTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.models import OCPEnabledTagKeys
from reporting.provider.gcp.models import GCPEnabledTagKeys


class OCPGCPTagView(TagView):
    """Get OpenShift-on-GCP tags."""

    provider = "ocp_gcp"
    serializer = OCPGCPTagsQueryParamSerializer
    query_handler = OCPGCPTagQueryHandler
    tag_handler = [GCPEnabledTagKeys, OCPEnabledTagKeys]
    tag_providers = [Provider.PROVIDER_GCP, Provider.PROVIDER_OCP]
    permission_classes = [GcpAccessPermission & OpenShiftAccessPermission]
