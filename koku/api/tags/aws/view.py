#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS tags."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.provider.models import Provider
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.aws.serializers import AWSTagsQueryParamSerializer
from api.tags.view import TagView


class AWSTagView(TagView):
    """Get AWS tags."""

    provider = "aws"
    serializer = AWSTagsQueryParamSerializer
    query_handler = AWSTagQueryHandler
    tag_providers = [Provider.PROVIDER_AWS]
    permission_classes = [AwsAccessPermission]
    set_cost_type_provider_map_kwarg = True
