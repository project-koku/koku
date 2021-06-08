#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS tags."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.serializers import AWSTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.aws.models import AWSTagsSummary


class AWSTagView(TagView):
    """Get AWS tags."""

    provider = "aws"
    serializer = AWSTagsQueryParamSerializer
    query_handler = AWSTagQueryHandler
    tag_handler = [AWSTagsSummary]
    permission_classes = [AwsAccessPermission]
