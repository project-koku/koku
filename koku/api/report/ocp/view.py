#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift Usage Reports."""
import logging

from rest_framework import status
from rest_framework.response import Response

from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.throttling import OcpTagQueryThrottle
from api.models import Provider
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import OCPCostBreakdownQueryParamSerializer
from api.report.ocp.serializers import OCPCostQueryParamSerializer
from api.report.ocp.serializers import OCPGpuQueryParamSerializer
from api.report.ocp.serializers import OCPInventoryQueryParamSerializer
from api.report.ocp.serializers import OCPMigProfilesQueryParamSerializer
from api.report.ocp.serializers import OCPVirtualMachinesQueryParamSerializer
from api.report.view import ReportView
from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor import OCP_GPU_COST_MODEL_UNLEASH_FLAG

LOG = logging.getLogger(__name__)


class OCPView(ReportView):
    """OCP Base View."""

    permission_classes = [OpenShiftAccessPermission]
    throttle_classes = [OcpTagQueryThrottle]
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


class OCPMigProfilesView(OCPView):
    """Get OpenShift MIG (Multi-Instance GPU) profile data.

    This endpoint returns MIG profile information without costs.
    Requires filter by vendor, model, and node.
    """

    report = "mig_profiles"
    serializer = OCPMigProfilesQueryParamSerializer

    def get(self, request, **kwargs):
        """Get MIG profiles data with Unleash flag protection."""
        schema = request.user.customer.schema_name

        if not is_feature_flag_enabled_by_schema(schema, OCP_GPU_COST_MODEL_UNLEASH_FLAG, dev_fallback=True):
            return Response(status=status.HTTP_403_FORBIDDEN)

        return super().get(request, **kwargs)


class OCPCostBreakdownView(OCPView):
    """Get OpenShift per-rate cost breakdown data."""

    report = "cost_breakdown"
    serializer = OCPCostBreakdownQueryParamSerializer

    @staticmethod
    def _build_tree(values):
        """Reconstruct a nested tree from flat breakdown rows using path/parent_path."""
        nodes = {}
        for item in values:
            path = item.get("path", "")
            if path in nodes:
                LOG.warning("Duplicate path in breakdown data, overwriting: %s", path)
            nodes[path] = {**item, "children": []}

        root = None
        for path, node in nodes.items():
            parent_path = node.get("parent_path", "")
            if parent_path and parent_path in nodes:
                nodes[parent_path]["children"].append(node)
            elif parent_path:
                LOG.warning("Orphan node in breakdown tree (parent_path=%s not found): %s", parent_path, path)
            if node.get("depth") == 1:
                root = node

        return root or {}

    @classmethod
    def _transform_to_tree(cls, data_item):
        """Recursively find 'values' lists and replace with nested 'tree'."""
        if isinstance(data_item, dict):
            if "values" in data_item:
                data_item["tree"] = cls._build_tree(data_item.pop("values"))
            else:
                for value in data_item.values():
                    cls._transform_to_tree(value)
        elif isinstance(data_item, list):
            for item in data_item:
                cls._transform_to_tree(item)

    def get(self, request, **kwargs):
        """Get cost breakdown with audit logging and optional tree view."""
        LOG.info(
            "cost_breakdown API request",
            extra={
                "user": getattr(request.user, "username", None),
                "path_params": dict(request.query_params),
            },
        )
        response = super().get(request, **kwargs)

        if request.query_params.get("view") == "tree" and hasattr(response, "data"):
            for date_group in response.data.get("data", []):
                self._transform_to_tree(date_group)

        return response
