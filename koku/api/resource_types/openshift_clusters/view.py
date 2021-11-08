#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift clusters."""
from django.db.models import F
from django.db.models.functions.comparison import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.ocp.models import OCPCostSummaryP


class OCPClustersView(generics.ListAPIView):
    """API GET list view for Openshift clusters."""

    queryset = (
        OCPCostSummaryP.objects.annotate(
            **{"value": F("cluster_id"), "ocp_cluster_alias": Coalesce(F("cluster_alias"), "cluster_id")}
        )
        .values("value", "ocp_cluster_alias")
        .distinct()
        .filter(cluster_id__isnull=False)
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [OpenShiftAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value", "ocp_cluster_alias"]
    search_fields = ["$value", "$ocp_cluster_alias"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift cluster id and displays values related to what the user has access to
        supported_query_params = ["search", "limit"]
        user_access = None
        error_message = {}
        # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        if request.user.admin:
            return super().list(request)
        if request.user.access:
            user_access = request.user.access.get("openshift.cluster", {}).get("read", [])
            # checks if the access exists, and the user has wildcard access
            if user_access and user_access[0] == "*":
                return super().list(request)
        self.queryset = self.queryset.filter(cluster_id__in=user_access)
        return super().list(request)
