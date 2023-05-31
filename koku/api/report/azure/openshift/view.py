#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift on Azure Usage Reports."""
from api.common.permissions.azure_access import AzureAccessPermission
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.models import Provider
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.openshift.serializers import OCPAzureQueryParamSerializer
from api.report.view import ReportView
from reporting.models import AzureEnabledTagKeys
from reporting.models import OCPEnabledTagKeys


class OCPAzureView(ReportView):
    """OCP+Azure Base View."""

    permission_classes = [AzureAccessPermission, OpenShiftAccessPermission]
    provider = Provider.OCP_AZURE
    serializer = OCPAzureQueryParamSerializer
    query_handler = OCPAzureReportQueryHandler
    tag_handler = [AzureEnabledTagKeys, OCPEnabledTagKeys]
    tag_providers = [Provider.PROVIDER_AZURE, Provider.PROVIDER_OCP]


class OCPAzureCostView(OCPAzureView):
    """Get OpenShift on Azure cost usage data."""

    report = "costs"


class OCPAzureInstanceTypeView(OCPAzureView):
    """Get OpenShift on Azure instance usage data."""

    report = "instance_type"


class OCPAzureStorageView(OCPAzureView):
    """Get OpenShift on Azure storage usage data."""

    report = "storage"
