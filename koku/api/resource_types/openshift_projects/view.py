#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift projects."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftProjectPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummary
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummary
from reporting.provider.ocp.models import OCPCostSummaryByProjectP


class OCPProjectsView(generics.ListAPIView):
    """API GET list view for Openshift projects."""

    queryset = (
        OCPCostSummaryByProjectP.objects.annotate(**{"value": F("namespace")})
        .values("value")
        .distinct()
        .filter(namespace__isnull=False)
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [OpenShiftProjectPermission | OpenShiftAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift projects namespace,displays values related to the users access
        supported_query_params = ["search", "limit", "cloud", "aws", "aws2"]
        error_message = {}
        query_holder = None
        # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
                elif key == "cloud":
                    cloud = self.request.query_params.get("cloud")
                    if cloud == "true":
                        self.awsqueryset = (
                            OCPAWSCostLineItemProjectDailySummary.objects.annotate(**{"value": F("namespace")})
                            .values("value")
                            .distinct()
                            .filter(namespace__isnull=False)
                        )
                        self.azurequeryset = (
                            OCPAzureCostLineItemProjectDailySummary.objects.annotate(**{"value": F("namespace")})
                            .values("value")
                            .distinct()
                            .filter(namespace__isnull=False)
                        )
                        self.queryset = self.awsqueryset.union(self.azurequeryset, all=True)
        if request.user.admin:
            return super().list(request)
        if request.user.access:
            ocp_project_access = request.user.access.get("openshift.project", {}).get("read", [])
            ocp_cluster_access = request.user.access.get("openshift.cluster", {}).get("read", [])
            query_holder = self.queryset
            if ocp_project_access and ocp_project_access[0] != "*":
                query_holder = query_holder.filter(namespace__in=ocp_project_access)
            if ocp_cluster_access and ocp_cluster_access[0] != "*":
                query_holder = query_holder.filter(cluster_id__in=ocp_cluster_access)
        self.queryset = query_holder
        return super().list(request)
