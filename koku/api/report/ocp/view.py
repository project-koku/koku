#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift Usage Reports."""
from rest_framework import status
from rest_framework.response import Response

from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import OCPCostQueryParamSerializer
from api.report.ocp.serializers import OCPGpuQueryParamSerializer
from api.report.ocp.serializers import OCPInventoryQueryParamSerializer
from api.report.ocp.serializers import OCPVirtualMachinesQueryParamSerializer
from api.report.view import ReportView
from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor import OCP_GPU_COST_MODEL_UNLEASH_FLAG


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


class OCPGpuView(OCPView):
    """Get OpenShift GPU usage data."""

    report = "gpu"
    serializer = OCPGpuQueryParamSerializer

    def get(self, request, **kwargs):
        """Get GPU report data with Unleash flag protection."""
        schema = request.user.customer.schema_name

        if not is_feature_flag_enabled_by_schema(schema, OCP_GPU_COST_MODEL_UNLEASH_FLAG, dev_fallback=True):
            return Response(status=status.HTTP_403_FORBIDDEN)

        return super().get(request, **kwargs)
