#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for GCP Regions."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.gcp_access import GcpAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.gcp.models import GCPCostSummaryByRegion


class GCPRegionView(generics.ListAPIView):
    """API GET list view for GCP Regions."""

    queryset = (
        GCPCostSummaryByRegion.objects.annotate(**{"value": F("region")})
        .values("value")
        .distinct()
        .filter(region__isnull=False)
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [GcpAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for GCP account id and displays values related to what the user has access to
        if request.user.admin:
            return super().list(request)
        elif request.user.access:
            user_access = request.user.access.get("gcp.account", {}).get("read", [])
        else:
            user_access = []
        self.queryset = self.queryset.values("value").filter(account_id__in=user_access)
        return super().list(request)
