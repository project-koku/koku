#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift GPU Models."""
from django.db.models import F
from reporting.provider.ocp.models import OCPGpuSummaryP
from api.resource_types.view import OCPGpuResourceTypesView


class OCPGpuModelsView(OCPGpuResourceTypesView):
    """API GET list view for Openshift GPU models."""

    queryset = (
        OCPGpuSummaryP.objects.annotate(**{"value": F("model_name")})
        .values("value")
        .distinct()
        .filter(model_name__isnull=False)
    )
