#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Azure Subscription guid."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.azure_access import AzureAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.azure.models import AzureCostSummaryByAccount


class AzureSubscriptionGuidView(generics.ListAPIView):
    """API GET list view for Azure Subscription Guid."""

    queryset = (
        AzureCostSummaryByAccount.objects.annotate(**{"value": F("subscription_guid")}).values("value").distinct()
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [AzureAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Azure subscription guid and displays values related to what the user has access to
        user_access = []
        if request.user.admin:
            return super().list(request)
        elif request.user.access:
            user_access = request.user.access.get("azure.subscription_guid", {}).get("read", [])
        self.queryset = self.queryset.values("value").filter(subscription_guid__in=user_access)
        return super().list(request)
