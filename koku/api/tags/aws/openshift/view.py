#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OCP-on-AWS tags."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.tags.aws.openshift.queries import OCPAWSTagQueryHandler
from api.tags.serializers import OCPAWSTagsQueryParamSerializer
from api.tags.view import TagView
from reporting.provider.aws.models import AWSTagsSummary


class OCPAWSTagView(TagView):
    """Get OpenShift-on-AWS tags."""

    provider = "ocp_aws"
    serializer = OCPAWSTagsQueryParamSerializer
    query_handler = OCPAWSTagQueryHandler
    tag_handler = [AWSTagsSummary]
    permission_classes = [AwsAccessPermission & OpenShiftAccessPermission]
