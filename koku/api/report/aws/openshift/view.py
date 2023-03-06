#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift on AWS Usage Reports."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
from api.report.aws.openshift.query_handler import OCPAWSReportQueryHandler
from api.report.aws.openshift.serializers import OCPAWSQueryParamSerializer
from api.report.view import ReportView
from reporting.models import AWSEnabledTagKeys


class OCPAWSView(ReportView):
    """OCP+AWS Base View."""

    permission_classes = [AwsAccessPermission, OpenShiftAccessPermission]
    provider = Provider.OCP_AWS
    serializer = OCPAWSQueryParamSerializer
    query_handler = OCPAWSReportQueryHandler
    tag_handler = [AWSEnabledTagKeys]


class OCPAWSCostView(OCPAWSView):
    """Get OpenShift on AWS cost usage data."""

    report = "costs"


class OCPAWSStorageView(OCPAWSView):
    """Get OpenShift on AWS storage usage data."""

    report = "storage"


class OCPAWSInstanceTypeView(OCPAWSView):
    """Get OpenShift on AWS instance usage data."""

    report = "instance_type"
