#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift nodes."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftNodePermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.ocp.models import OCPCostSummaryByNode


class OCPNodesView(generics.ListAPIView):
    """API GET list view for Openshift nodes."""

    queryset = (
        OCPCostSummaryByNode.objects.annotate(**{"value": F("node")})
        .values("value")
        .distinct()
        .filter(node__isnull=False)
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [OpenShiftNodePermission | OpenShiftAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift nodes and displays values that the user has access too
        supported_query_params = ["search", "limit"]
        error_message = {}
        query_holder = None
        # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        if request.user.admin:
            return super().list(request)
        if request.user.access:
            ocp_node_access = request.user.access.get("openshift.node", {}).get("read", [])
            ocp_cluster_access = request.user.access.get("openshift.cluster", {}).get("read", [])
            # checks if the access exists, and the user has wildcard access
            if ocp_node_access and ocp_node_access[0] == "*" or ocp_cluster_access and ocp_cluster_access[0] == "*":
                return super().list(request)
            query_holder = self.queryset
            if ocp_node_access:
                query_holder = query_holder.filter(node__in=ocp_node_access)
            if ocp_cluster_access:
                query_holder = query_holder.filter(cluster_id__in=ocp_cluster_access)
        # if query_holder does not exist we return an empty queryset
        self.queryset = query_holder
        return super().list(request)
