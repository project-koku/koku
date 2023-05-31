#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI views."""
from api.common.permissions.oci_access import OCIAccessPermission
from api.models import Provider
from api.report.oci.query_handler import OCIReportQueryHandler
from api.report.oci.serializers import OCIQueryParamSerializer
from api.report.view import ReportView
from reporting.provider.oci.models import OCIEnabledTagKeys


class OCIView(ReportView):
    """OCI Base View."""

    permission_classes = [OCIAccessPermission]
    provider = Provider.PROVIDER_OCI
    serializer = OCIQueryParamSerializer
    query_handler = OCIReportQueryHandler
    tag_handler = [OCIEnabledTagKeys]
    tag_providers = [Provider.PROVIDER_OCI]


class OCICostView(OCIView):
    """Get cost data."""

    report = "costs"


class OCIInstanceTypeView(OCIView):
    """Get inventory data."""

    report = "instance_type"


class OCIStorageView(OCIView):
    """Get inventory storage data."""

    report = "storage"
