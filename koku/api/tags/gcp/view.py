#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for GCP tags."""
from api.common.permissions.gcp_access import GcpAccessPermission
from api.tags.gcp.queries import GCPTagQueryHandler
from api.tags.serializers import GCPTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.gcp.models import GCPTagsSummary


class GCPTagView(TagView):
    """Get GCP tags."""

    provider = "gcp"
    serializer = GCPTagsQueryParamSerializer
    query_handler = GCPTagQueryHandler
    tag_handler = [GCPTagsSummary]
    permission_classes = [GcpAccessPermission]
