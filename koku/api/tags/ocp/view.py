#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift tags."""
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.provider.models import Provider
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.serializers import OCPTagsQueryParamSerializer
from api.tags.view import TagView


class OCPTagView(TagView):
    """Get OpenShift tags."""

    provider = "ocp"
    serializer = OCPTagsQueryParamSerializer
    query_handler = OCPTagQueryHandler
    tag_providers = [Provider.PROVIDER_OCP]
    permission_classes = [OpenShiftAccessPermission]
