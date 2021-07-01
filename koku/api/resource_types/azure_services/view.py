#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Azure Service types."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.resource_type_access import ResourceTypeAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.azure.models import AzureCostSummaryByService


class AzureServiceView(generics.ListAPIView):
    """API GET list view for Azure Service types."""

    queryset = (
        AzureCostSummaryByService.objects.annotate(**{"value": F("service_name")})
        .values("value")
        .distinct()
        .filter(service_name__isnull=False)
    )

    serializer_class = ResourceTypeSerializer
    permission_classes = [ResourceTypeAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        return super().list(request)
