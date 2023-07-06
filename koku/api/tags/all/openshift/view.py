#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCP-on-All tags."""
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.provider.models import Provider
from api.tags.all.openshift.queries import OCPAllTagQueryHandler
from api.tags.all.openshift.serializers import OCPAllTagsQueryParamSerializer
from api.tags.view import TagView


class OCPAllTagView(TagView):
    """Get OpenShift-on-All tags."""

    provider = "ocp_all"
    serializer = OCPAllTagsQueryParamSerializer
    query_handler = OCPAllTagQueryHandler
    tag_providers = [Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE, Provider.PROVIDER_GCP, Provider.PROVIDER_OCP]
    permission_classes = [OpenshiftAllAccessPermission]
