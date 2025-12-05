#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift GPU resource types."""
from django.db.models import F

from api.resource_types.view import OCPGpuResourceTypesView
from reporting.provider.ocp.models import OCPGpuSummaryP


class OCPGpuModelsView(OCPGpuResourceTypesView):
    """API GET list view for Openshift GPU models."""

    query_filter_keys = OCPGpuResourceTypesView.query_filter_keys + ["vendor_name"]

    queryset = (
        OCPGpuSummaryP.objects.annotate(**{"value": F("model_name")})
        .values("value")
        .distinct()
        .filter(model_name__isnull=False)
    )


class OCPGpuVendorsView(OCPGpuResourceTypesView):
    """API GET list view for Openshift GPU vendors."""

    queryset = (
        OCPGpuSummaryP.objects.annotate(**{"value": F("vendor_name")})
        .values("value")
        .distinct()
        .filter(vendor_name__isnull=False)
    )
