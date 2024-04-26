#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift Usage Reports."""
from rest_framework.pagination import Response
from rest_framework.views import status

from api.common.pagination import ReportPagination
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
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

        response_fixture = {
            "total": {
                "usage": {
                    "value": 3.6801746441,
                    "units": "GB",
                },
                "data_transfer_in": {
                    "value": 12.82510775,
                    "units": "GB",
                },
                "data_transfer_out": {
                    "value": 8.080656137,
                    "units": "GB",
                },
                "infrastructure": {
                    "raw": {"value": 1945.51192915, "units": "USD"},
                    "markup": {"value": 0.0, "units": "USD"},
                    "usage": {"value": 0.0, "units": "USD"},
                    "total": {"value": 1945.51192915, "units": "USD"},
                },
                "supplementary": {
                    "raw": {"value": 0.0, "units": "USD"},
                    "markup": {"value": 0.0, "units": "USD"},
                    "usage": {"value": 0.0, "units": "USD"},
                    "total": {"value": 0.0, "units": "USD"},
                },
                "cost": {
                    "raw": {"value": 4863.77982288, "units": "USD"},
                    "markup": {"value": 0.0, "units": "USD"},
                    "usage": {"value": 0.0, "units": "USD"},
                    "total": {"value": 4863.77982288, "units": "USD"},
                },
            },
            "data": [
                {
                    "date": "2024-03-31",
                    "values": [
                        {
                            "date": "2024-03-31",
                            "data_transfer_in": {
                                "value": 3.6801746441,
                                "units": "GB",
                            },
                            "data_transfer_out": {
                                "value": 2.6866746441,
                                "units": "GB",
                            },
                            "resource_id": "i-727f8dc9c567f1552",
                            "clusters": ["Test OCP on AWS"],
                            "source_uuid": "6795d5e6-951c-4382-a8d3-390515d7ec3d",
                            "region": "us-east-1",
                            "infrastructure": {
                                "raw": {"value": 1945.51192915, "units": "USD"},
                                "markup": {"value": 0.0, "units": "USD"},
                                "usage": {"value": 0.0, "units": "USD"},
                                "total": {"value": 1945.5119291598, "units": "USD"},
                            },
                            "supplementary": {
                                "raw": {"value": 0.0, "units": "USD"},
                                "markup": {"value": 0.0, "units": "USD"},
                                "usage": {"value": 0.0, "units": "USD"},
                                "total": {"value": 0.0, "units": "USD"},
                            },
                            "cost": {
                                "raw": {"value": 1945.51192915, "units": "USD"},
                                "markup": {"value": 0.0, "units": "USD"},
                                "usage": {"value": 0.0, "units": "USD"},
                                "total": {"value": 1945.51192915, "units": "USD"},
                            },
                        },
                    ],
                },
                {
                    "date": "2024-04-01",
                    "values": [
                        {
                            "date": "2024-04-01",
                            "data_transfer_in": {
                                "value": 9.1449331092,
                                "units": "GB",
                            },
                            "data_transfer_out": {
                                "value": 5.3939814929,
                                "units": "GB",
                            },
                            "resource_id": "i-727f8dc9c567f1552",
                            "clusters": ["Test OCP on AWS"],
                            "source_uuid": "6795d5e6-951c-4382-a8d3-390515d7ec3d",
                            "region": "us-east-1",
                            "infrastructure": {
                                "raw": {"value": 2918.26789372, "units": "USD"},
                                "markup": {"value": 0.0, "units": "USD"},
                                "usage": {"value": 0.0, "units": "USD"},
                                "total": {"value": 2918.26789372, "units": "USD"},
                            },
                            "supplementary": {
                                "raw": {"value": 0.0, "units": "USD"},
                                "markup": {"value": 0.0, "units": "USD"},
                                "usage": {"value": 0.0, "units": "USD"},
                                "total": {"value": 0.0, "units": "USD"},
                            },
                            "cost": {
                                "raw": {"value": 2918.267893725, "units": "USD"},
                                "markup": {"value": 0.0, "units": "USD"},
                                "usage": {"value": 0.0, "units": "USD"},
                                "total": {"value": 2918.267893725, "units": "USD"},
                            },
                        }
                    ],
                },
            ],
        }
        paginator = ReportPagination()
        paginated_result = paginator.paginate_queryset(response_fixture, request)
        return paginator.get_paginated_response(paginated_result)
