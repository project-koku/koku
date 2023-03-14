#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCI tags."""
from api.common.permissions.oci_access import OCIAccessPermission
from api.tags.oci.queries import OCITagQueryHandler
from api.tags.oci.serializers import OCITagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.oci.models import OCIEnabledTagKeys


class OCITagView(TagView):
    """Get OCI tags."""

    provider = "oci"
    serializer = OCITagsQueryParamSerializer
    query_handler = OCITagQueryHandler
    tag_handler = [OCIEnabledTagKeys]
    permission_classes = [OCIAccessPermission]
