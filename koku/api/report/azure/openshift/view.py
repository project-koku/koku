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
"""View for OpenShift on Azure Usage Reports."""
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.openshift.serializers import OCPAzureQueryParamSerializer
from api.report.view import ReportView
from reporting.models import OCPAzureTagsSummary


class OCPAzureView(ReportView):
    """OCP+Azure Base View."""

    permission_classes = [AzureAccessPermission, OpenShiftAccessPermission]
    provider = Provider.OCP_AZURE
    serializer = OCPAzureQueryParamSerializer
    query_handler = OCPAzureReportQueryHandler
    tag_handler = [OCPAzureTagsSummary]


class OCPAzureCostView(OCPAzureView):
    """Get OpenShift on Azure cost usage data."""

    report = "costs"


class OCPAzureInstanceTypeView(OCPAzureView):
    """Get OpenShift on Azure instance usage data."""

    report = "instance_type"


class OCPAzureStorageView(OCPAzureView):
    """Get OpenShift on Azure storage usage data."""

    report = "storage"
