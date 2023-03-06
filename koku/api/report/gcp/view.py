#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP views."""
from api.common.permissions.gcp_access import GcpAccessPermission
from api.models import Provider
from api.report.gcp.query_handler import GCPReportQueryHandler
from api.report.gcp.serializers import GCPQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.gcp.models import GCPEnabledTagKeys


class GCPView(ReportView):
    """GCP Base View."""

    permission_classes = [GcpAccessPermission]
    provider = Provider.PROVIDER_GCP
    serializer = GCPQueryParamSerializer
    query_handler = GCPReportQueryHandler
    tag_handler = [GCPEnabledTagKeys]


class GCPCostView(GCPView):
    """Get cost data."""

    report = "costs"


class GCPInstanceTypeView(GCPView):
    """Get inventory data."""

    report = "instance_type"


class GCPStorageView(GCPView):
    """Get inventory storage data."""

    report = "storage"
