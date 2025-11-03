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
from api.report.ocp.serializers import OCPVirtualMachinesQueryParamSerializer
from api.report.view import ReportView


class OCPView(ReportView):
    """OCP Base View."""

    permission_classes = [OpenShiftAccessPermission]
    provider = Provider.PROVIDER_OCP
    serializer = OCPInventoryQueryParamSerializer
    query_handler = OCPReportQueryHandler
    tag_providers = [Provider.PROVIDER_OCP]


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


class OCPNetworkView(OCPView):
    """OpenShift node network usage"""

    report = "network"


class OCPReportVirtualMachinesView(OCPView):
    """Get OpenShift Virtual Machines data."""

    report = "virtual_machines"
    serializer = OCPVirtualMachinesQueryParamSerializer
    only_monthly_resolution = True
    monthly_pagination_key = "vm_names"
