#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift virtual machines."""
from django.conf import settings
from django.db.models import F
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ResourceTypeViewPaginator
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftProjectPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.ocp.models import OCPVirtualMachineSummaryP


class OCPVirtualMachinesView(generics.ListAPIView):
    """API GET list view for Openshift virtual machines."""

    serializer_class = ResourceTypeSerializer
    permission_classes = [OpenShiftProjectPermission | OpenShiftAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["value"]
    pagination_class = ResourceTypeViewPaginator

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift virtual machines, displays values related to the users access
        supported_query_params = ["search", "limit"]
        query_filter_keys = ["cluster_id", "cluster_alias", "namespace", "node"]
        supported_query_params.extend(query_filter_keys)
        query_filter_map = {"vm_name__isnull": False}
        error_message = {}
        query_holder = None

        # check for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
                if key in query_filter_keys:
                    query_filter_map[f"{key}__icontains"] = self.request.query_params.get(key)

        query_filters = Q(**query_filter_map)
        self.queryset = (
            OCPVirtualMachineSummaryP.objects.annotate(value=F("vm_name"))
            .values("value")
            .distinct()
            .filter(query_filters)
        )

        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
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
