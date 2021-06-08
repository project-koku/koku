#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCP-on-All tags."""
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.tags.all.openshift.queries import OCPAllTagQueryHandler
from api.tags.serializers import OCPAllTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.aws.models import AWSTagsSummary
from reporting.provider.azure.models import AzureTagsSummary


class OCPAllTagView(TagView):
    """Get OpenShift-on-All tags."""

    provider = "ocp_all"
    serializer = OCPAllTagsQueryParamSerializer
    query_handler = OCPAllTagQueryHandler
    tag_handler = [AWSTagsSummary, AzureTagsSummary]
    permission_classes = [OpenshiftAllAccessPermission]
