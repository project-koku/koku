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
"""View for OpenShift on All infrastructure Usage Reports."""
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.models import Provider
from api.report.all.openshift.query_handler import OCPAllReportQueryHandler
from api.report.all.openshift.serializers import OCPAllQueryParamSerializer
from api.report.view import ReportView
from reporting.models import OCPAWSTagsSummary
from reporting.models import OCPAzureTagsSummary


class OCPAllView(ReportView):
    """OCP on All Infrastructure Base View."""

    permission_classes = [OpenshiftAllAccessPermission]
    provider = Provider.OCP_ALL
    serializer = OCPAllQueryParamSerializer
    query_handler = OCPAllReportQueryHandler
    tag_handler = [OCPAWSTagsSummary, OCPAzureTagsSummary]


class OCPAllCostView(OCPAllView):
    """Get OpenShift on All Infrastructure cost usage data."""

    report = "costs"


class OCPAllStorageView(OCPAllView):
    """Get OpenShift on All Infrastructure storage usage data."""

    report = "storage"


class OCPAllInstanceTypeView(OCPAllView):
    """Get OpenShift on All Infrastructure instance usage data."""

    report = "instance_type"
