#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Azure Subscription guid."""
from django.conf import settings
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.filters import SearchFilterResourceTypes
from api.common.pagination import ResourceTypeViewPaginator
from api.common.permissions.azure_access import AzureAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.azure.models import AzureCostSummaryByAccountP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryByAccountP


class AzureSubscriptionGuidView(generics.ListAPIView):
    """API GET list view for Azure Subscription Guid."""

    queryset = (
        AzureCostSummaryByAccountP.objects.annotate(
            **(
                {
                    "value": F("subscription_guid"),
                    "alias": Coalesce(F("subscription_name"), "subscription_guid"),
                }
            )
        )
        .values("value", "alias")
        .distinct()
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [AzureAccessPermission]
    filter_backends = [filters.OrderingFilter, SearchFilterResourceTypes]
    ordering = ["value", "alias"]
    search_fields = ["value", "alias"]
    pagination_class = ResourceTypeViewPaginator

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Azure subscription guid and displays values related to what the user has access to
        supported_query_params = ["search", "limit", "openshift"]
        user_access = []
        error_message = {}
        # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
                elif key == "openshift":
                    openshift = self.request.query_params.get("openshift")
                    if openshift == "true":
                        self.queryset = (
                            OCPAzureCostSummaryByAccountP.objects.annotate(
                                **{
                                    "value": F("subscription_guid"),
                                    "alias": Coalesce(F("subscription_name"), "subscription_guid"),
                                }
                            )
                            .values("value", "alias")
                            .distinct()
                        )

        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return super().list(request)
        elif request.user.access:
            user_access = request.user.access.get("azure.subscription_guid", {}).get("read", [])
        if user_access and user_access[0] == "*":
            return super().list(request)
        self.queryset = self.queryset.filter(subscription_guid__in=user_access)

        return super().list(request)
