#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""View for OpenShift on AWS Usage Reports."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
from api.report.ocp_aws.query_handler import OCPAWSReportQueryHandler
from api.report.ocp_aws.serializers import OCPAWSQueryParamSerializer
from api.report.view import ReportView
from reporting.models import OCPAWSTagsSummary


class OCPAWSView(ReportView):
    """OCP+AWS Base View."""

    permission_classes = [AwsAccessPermission, OpenShiftAccessPermission]
    provider = Provider.OCP_AWS
    serializer = OCPAWSQueryParamSerializer
    query_handler = OCPAWSReportQueryHandler
    tag_handler = [OCPAWSTagsSummary]


class OCPAWSCostView(OCPAWSView):
    """Get OpenShift on AWS cost usage data."""

    report = "costs"


class OCPAWSStorageView(OCPAWSView):
    """Get OpenShift on AWS storage usage data."""

    report = "storage"


class OCPAWSInstanceTypeView(OCPAWSView):
    """Get OpenShift on AWS instance usage data."""

    report = "instance_type"
