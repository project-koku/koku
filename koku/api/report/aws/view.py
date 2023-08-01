#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS views."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.aws_access import AWSOUAccessPermission
from api.models import Provider
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.serializers import AWSQueryParamSerializer
from api.report.view import ReportView


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
