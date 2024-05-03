#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift Usage Reports."""
import dataclasses

from rest_framework.pagination import Response
from rest_framework.views import status

from api.common.pagination import ReportPagination
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
from api.report.ocp.network.example import ExampleResponseBody
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import OCPCostQueryParamSerializer
from api.report.ocp.serializers import OCPInventoryQueryParamSerializer
from api.report.view import ReportView
from koku.feature_flags import fallback_development_true
from koku.feature_flags import UNLEASH_CLIENT


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

    def get(self, request, **kwargs):
        if not UNLEASH_CLIENT.is_enabled(
            "cost-management.backend.feature-cost-3761-node-network", fallback_function=fallback_development_true
        ):
            return Response(data="Under development", status=status.HTTP_400_BAD_REQUEST)

        data = ExampleResponseBody.generate()
        paginator = ReportPagination()
        paginated_result = paginator.paginate_queryset(dataclasses.asdict(data), request)
        return paginator.get_paginated_response(paginated_result)
