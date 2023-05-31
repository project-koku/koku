#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for OpenShift on All infrastructure Usage Reports."""
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.models import Provider
from api.report.all.openshift.query_handler import OCPAllReportQueryHandler
from api.report.all.openshift.serializers import OCPAllQueryParamSerializer
from api.report.view import ReportView
from reporting.models import AWSEnabledTagKeys
from reporting.models import AzureEnabledTagKeys
from reporting.models import GCPEnabledTagKeys
from reporting.models import OCPEnabledTagKeys


class OCPAllView(ReportView):
    """OCP on All Infrastructure Base View."""

    permission_classes = [OpenshiftAllAccessPermission]
    provider = Provider.OCP_ALL
    serializer = OCPAllQueryParamSerializer
    query_handler = OCPAllReportQueryHandler
    tag_providers = [Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE, Provider.PROVIDER_GCP, Provider.PROVIDER_OCP]
    tag_handler = [AWSEnabledTagKeys, AzureEnabledTagKeys, GCPEnabledTagKeys, OCPEnabledTagKeys]


class OCPAllCostView(OCPAllView):
    """Get OpenShift on All Infrastructure cost usage data."""

    report = "costs"


class OCPAllStorageView(OCPAllView):
    """Get OpenShift on All Infrastructure storage usage data."""

    report = "storage"


class OCPAllInstanceTypeView(OCPAllView):
    """Get OpenShift on All Infrastructure instance usage data."""

    report = "instance_type"
