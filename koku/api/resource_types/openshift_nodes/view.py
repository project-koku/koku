#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift nodes."""
from django.conf import settings
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.filters import SearchFilterResourceTypes
from api.common.pagination import ResourceTypeViewPaginator
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftNodePermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.all.openshift.models import OCPAllCostLineItemProjectDailySummaryP
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.provider.gcp.openshift.models import OCPGCPCostLineItemProjectDailySummaryP
from reporting.provider.ocp.models import OCPCostSummaryByNodeP

CLOUD_PARAMS = {"aws", "azure", "gcp", "all_cloud"}

CLOUD_MODEL_MAP_NODES = {
    "aws": OCPAWSCostLineItemProjectDailySummaryP,
    "azure": OCPAzureCostLineItemProjectDailySummaryP,
    "gcp": OCPGCPCostLineItemProjectDailySummaryP,
    "all_cloud": OCPAllCostLineItemProjectDailySummaryP,
}


class OCPNodesView(generics.ListAPIView):
    """API GET list view for Openshift nodes."""

    queryset = (
        OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
        .values("value")
        .distinct()
        .filter(node__isnull=False)
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [OpenShiftNodePermission | OpenShiftAccessPermission]
    filter_backends = [filters.OrderingFilter, SearchFilterResourceTypes]
    ordering = ["value"]
    search_fields = ["value"]
    pagination_class = ResourceTypeViewPaginator

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift nodes and displays values that the user has access too
        supported_query_params = ["search", "limit", "aws", "azure", "gcp", "all_cloud"]
        error_message = {}
        query_holder = None
        # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        # Check for cloud provider filtering
        active_cloud_params = [p for p in CLOUD_PARAMS if self.request.query_params.get(p) == "true"]
        if len(active_cloud_params) > 1:
            error_message = {
                p: [{"Only one cloud provider parameter can be supplied at a time."}] for p in active_cloud_params
            }
            return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        if active_cloud_params:
            model = CLOUD_MODEL_MAP_NODES[active_cloud_params[0]]
            self.queryset = (
                model.objects.annotate(**{"value": F("node")}).values("value").distinct().filter(node__isnull=False)
            )
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return super().list(request)
        if request.user.access:
            ocp_node_access = request.user.access.get("openshift.node", {}).get("read", [])
            ocp_cluster_access = request.user.access.get("openshift.cluster", {}).get("read", [])
            query_holder = self.queryset
            if ocp_node_access and ocp_node_access[0] != "*":
                query_holder = query_holder.filter(node__in=ocp_node_access)
            if ocp_cluster_access and ocp_cluster_access[0] != "*":
                query_holder = query_holder.filter(cluster_id__in=ocp_cluster_access)
        self.queryset = query_holder
        return super().list(request)
