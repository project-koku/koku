#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCP-on-All tags."""
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.tags.all.openshift.queries import OCPAllTagQueryHandler
from api.tags.all.openshift.serializers import OCPAllTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.azure.models import AzureEnabledTagKeys
from reporting.provider.gcp.models import GCPEnabledTagKeys


class OCPAllTagView(TagView):
    """Get OpenShift-on-All tags."""

    provider = "ocp_all"
    serializer = OCPAllTagsQueryParamSerializer
    query_handler = OCPAllTagQueryHandler
    tag_handler = [AWSEnabledTagKeys, AzureEnabledTagKeys, GCPEnabledTagKeys]
    permission_classes = [OpenshiftAllAccessPermission]
