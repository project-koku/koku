#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift on GCP Usage Reports."""
# Done
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
from api.report.gcp.openshift.query_handler import OCPGCPReportQueryHandler
from api.report.gcp.openshift.serializers import OCPGCPQueryParamSerializer
from api.report.view import ReportView
from reporting.models import OCPGCPTagsSummary


class OCPGCPView(ReportView):
    """OCP+GCP Base View."""

    permission_classes = [GcpAccessPermission, OpenShiftAccessPermission]
    provider = Provider.OCP_GCP
    serializer = OCPGCPQueryParamSerializer
    query_handler = OCPGCPReportQueryHandler
    tag_handler = [OCPGCPTagsSummary]


class OCPGCPCostView(OCPGCPView):
    """Get OpenShift on GCP cost usage data."""

    report = "costs"


class OCPGCPStorageView(OCPGCPView):
    """Get OpenShift on GCP storage usage data."""

    report = "storage"


class OCPGCPInstanceTypeView(OCPGCPView):
    """Get OpenShift on GCP instance usage data."""

    report = "instance_type"
