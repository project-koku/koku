#
# Copyright 2019 Red Hat, Inc.
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
"""Azure views."""
from api.common.permissions.azure_access import AzureAccessPermission
from api.models import Provider
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.azure.serializers import AzureQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.azure.models import AzureTagsSummary


class AzureView(ReportView):
    """Azure Base View."""

    permission_classes = [AzureAccessPermission]
    provider = Provider.PROVIDER_AZURE
    serializer = AzureQueryParamSerializer
    query_handler = AzureReportQueryHandler
    tag_handler = [AzureTagsSummary]


class AzureCostView(AzureView):
    """Get cost data."""

    report = "costs"


class AzureInstanceTypeView(AzureView):
    """Get inventory data."""

    report = "instance_type"


class AzureStorageView(AzureView):
    """Get inventory storage data."""

    report = "storage"
