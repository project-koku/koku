#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for GCP Projects."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.gcp_access import GcpProjectPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.gcp.models import GCPTopology


class GCPProjectsView(generics.ListAPIView):
    """API GET list view for GCP projects."""

    queryset = GCPTopology.objects.annotate(**{"value": F("project_id")}).values("value").distinct()
    serializer_class = ResourceTypeSerializer
    permission_classes = [GcpProjectPermission | GcpAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for GCP project id and displays values related to what the user has access to
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
            gcp_account_access = request.user.access.get("gcp.account", {}).get("read", [])
            gcp_project_access = request.user.access.get("gcp.project", {}).get("read", [])
            # Checks if the access exists, and the user has wildcard access
            query_holder = self.queryset
            if gcp_project_access and gcp_project_access[0] != "*":
                query_holder = query_holder.filter(project_id__in=gcp_project_access)
            if gcp_account_access and gcp_account_access[0] != "*":
                query_holder = query_holder.filter(account_id__in=gcp_account_access)
        self.queryset = query_holder
        return super().list(request)
