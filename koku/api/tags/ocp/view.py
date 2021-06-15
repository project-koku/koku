#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift tags."""
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.serializers import OCPTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.ocp.models import OCPStorageVolumeLabelSummary
from reporting.provider.ocp.models import OCPUsagePodLabelSummary


class OCPTagView(TagView):
    """Get OpenShift tags."""

    provider = "ocp"
    serializer = OCPTagsQueryParamSerializer
    query_handler = OCPTagQueryHandler
    tag_handler = [OCPUsagePodLabelSummary, OCPStorageVolumeLabelSummary]
    permission_classes = [OpenShiftAccessPermission]
