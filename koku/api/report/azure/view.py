#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure views."""
from api.common.permissions.azure_access import AzureAccessPermission
from api.models import Provider
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.azure.serializers import AzureQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.azure.models import AzureEnabledTagKeys


class AzureView(ReportView):
    """Azure Base View."""

    permission_classes = [AzureAccessPermission]
    provider = Provider.PROVIDER_AZURE
    serializer = AzureQueryParamSerializer
    query_handler = AzureReportQueryHandler
    tag_handler = [AzureEnabledTagKeys]


class AzureCostView(AzureView):
    """Get cost data."""

    report = "costs"


class AzureInstanceTypeView(AzureView):
    """Get inventory data."""

    report = "instance_type"


class AzureStorageView(AzureView):
    """Get inventory storage data."""

    report = "storage"
