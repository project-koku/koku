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
"""AWS views."""
from api.common.permissions.aws_access import AwsAccessPermission
from api.models import Provider
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.serializers import QueryParamSerializer
from api.report.view import ReportView
from reporting.provider.aws.models import AWSTagsSummary


class AWSView(ReportView):
    """AWS Base View."""

    permission_classes = [AwsAccessPermission]
    provider = Provider.PROVIDER_AWS
    serializer = QueryParamSerializer
    query_handler = AWSReportQueryHandler
    tag_handler = [AWSTagsSummary]


class AWSCostView(AWSView):
    """Get cost data."""

    report = "costs"


class AWSInstanceTypeView(AWSView):
    """Get inventory data."""

    report = "instance_type"


class AWSStorageView(AWSView):
    """Get inventory storage data."""

    report = "storage"
