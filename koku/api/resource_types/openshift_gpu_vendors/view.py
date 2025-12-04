#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift GPU Vendors."""
from django.db.models import F

from api.resource_types.view import OCPGpuResourceTypesView
from reporting.provider.ocp.models import OCPGpuSummaryP


class OCPGpuVendorsView(OCPGpuResourceTypesView):
    """API GET list view for Openshift GPU vendors."""

    queryset = (
        OCPGpuSummaryP.objects.annotate(**{"value": F("vendor_name")})
        .values("value")
        .distinct()
        .filter(vendor_name__isnull=False)
    )
