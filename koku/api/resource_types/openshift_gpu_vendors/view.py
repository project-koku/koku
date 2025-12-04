#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift GPU Vendors."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from reporting.provider.ocp.models import OCPGpuSummaryP
from api.resource_types.view import OCPGpuResourceTypesView


class OCPGpuVendorsView(OCPGpuResourceTypesView):
    """API GET list view for Openshift GPU vendors."""

    queryset = (
        OCPGpuSummaryP.objects.annotate(**{"value": F("vendor_name")})
        .values("value")
        .distinct()
        .filter(vendor_name__isnull=False)
    )
