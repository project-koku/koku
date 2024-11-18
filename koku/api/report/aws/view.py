#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS views."""
from rest_framework.exceptions import NotFound

from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.aws_access import AWSOUAccessPermission
from api.models import Provider
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.serializers import AWSEC2ComputeQueryParamSerializer
from api.report.aws.serializers import AWSQueryParamSerializer
from api.report.view import ReportView
from masu.processor import is_feature_cost_4403_ec2_compute_cost_enabled


class AWSView(ReportView):
    """AWS Base View."""

    permission_classes = [AwsAccessPermission | AWSOUAccessPermission]
    provider = Provider.PROVIDER_AWS
    serializer = AWSQueryParamSerializer
    query_handler = AWSReportQueryHandler
    tag_providers = [Provider.PROVIDER_AWS]


class AWSCostView(AWSView):
    """Get cost data."""

    report = "costs"


class AWSInstanceTypeView(AWSView):
    """Get inventory data."""

    report = "instance_type"


class AWSStorageView(AWSView):
    """Get inventory storage data."""

    report = "storage"


class AWSEC2ComputeView(AWSView):
    """Get EC2 Compute data."""

    report = "ec2_compute"
    serializer = AWSEC2ComputeQueryParamSerializer
    monthly_pagination_key = "resource_ids"
    only_monthly_resolution = True

    def get(self, request, **kwargs):
        if not is_feature_cost_4403_ec2_compute_cost_enabled(request.user.customer.schema_name):
            raise NotFound()
        return super().get(request, **kwargs)
