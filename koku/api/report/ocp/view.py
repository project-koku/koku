#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift Usage Reports."""
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import OCPCostQueryParamSerializer
from api.report.ocp.serializers import OCPInventoryQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.ocp.models import OCPStorageVolumeLabelSummary
from reporting.provider.ocp.models import OCPUsagePodLabelSummary


class OCPView(ReportView):
    """OCP Base View."""

    permission_classes = [OpenShiftAccessPermission]
    provider = Provider.PROVIDER_OCP
    serializer = OCPInventoryQueryParamSerializer
    query_handler = OCPReportQueryHandler
    tag_handler = [OCPUsagePodLabelSummary, OCPStorageVolumeLabelSummary]


class OCPMemoryView(OCPView):
    """Get OpenShift memory usage data."""

    report = "memory"


class OCPCpuView(OCPView):
    """Get OpenShift compute usage data."""

    report = "cpu"


class OCPCostView(OCPView):
    """Get OpenShift cost data."""

    report = "costs"
    serializer = OCPCostQueryParamSerializer


class OCPVolumeView(OCPView):
    """Get OpenShift volume usage data."""

    report = "volume"
