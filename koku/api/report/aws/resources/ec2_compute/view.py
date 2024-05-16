#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS EC2 Compute views."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.aws_access import AWSOUAccessPermission
from api.models import Provider
from api.report.aws.resources.ec2_compute.query_handler import AWSEC2ComputeReportQueryHandler
from api.report.aws.resources.ec2_compute.serializers import AWSEC2ComputeQueryParamSerializer
from api.report.view import ReportView


class AWSEC2ComputeView(ReportView):
    """AWS Base View."""

    permission_classes = [AwsAccessPermission | AWSOUAccessPermission]
    provider = Provider.PROVIDER_AWS
    serializer = AWSEC2ComputeQueryParamSerializer
    query_handler = AWSEC2ComputeReportQueryHandler
    tag_providers = [Provider.PROVIDER_AWS]


class AWSEC2ComputeCostView(AWSEC2ComputeView):
    """Get cost data."""

    report = "costs"


class AWSEC2ComputeInstanceTypeView(AWSEC2ComputeView):
    """Get inventory data."""

    report = "instance_type"


class AWSEC2ComputeStorageView(AWSEC2ComputeView):
    """Get inventory storage data."""

    report = "storage"
