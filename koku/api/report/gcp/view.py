#
# Copyright 2020 Red Hat, Inc.
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
"""GCP views."""
from api.common.permissions.gcp_access import GcpAccessPermission
from api.models import Provider
from api.report.gcp.query_handler import GCPReportQueryHandler
from api.report.gcp.serializers import GCPQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.gcp.models import GCPTagsSummary


class GCPView(ReportView):
    """GCP Base View."""

    permission_classes = [GcpAccessPermission]
    provider = Provider.PROVIDER_GCP
    serializer = GCPQueryParamSerializer
    query_handler = GCPReportQueryHandler
    tag_handler = [GCPTagsSummary]


class GCPCostView(GCPView):
    """Get cost data."""

    report = "costs"


class GCPInstanceTypeView(GCPView):
    """Get inventory data."""

    report = "instance_type"


class GCPStorageView(GCPView):
    """Get inventory storage data."""

    report = "storage"
