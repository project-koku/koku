#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCP-on-GCP tags."""
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.tags.gcp.openshift.queries import OCPGCPTagQueryHandler
from api.tags.serializers import OCPGCPTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.gcp.models import GCPTagsSummary


class OCPGCPTagView(TagView):
    """Get OpenShift-on-GCP tags."""

    provider = "ocp_gcp"
    serializer = OCPGCPTagsQueryParamSerializer
    query_handler = OCPGCPTagQueryHandler
    tag_handler = [GCPTagsSummary]
    permission_classes = [GcpAccessPermission & OpenShiftAccessPermission]
