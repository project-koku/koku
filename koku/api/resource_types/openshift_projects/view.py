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
from api.common.permissions.openshift_access import OpenShiftProjectPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.ocp.models import OCPCostSummaryByProject


class OCPProjectsView(generics.ListAPIView):
    """API GET list view for Openshift projects."""

    queryset = (
        OCPCostSummaryByProject.objects.annotate(**{"value": F("namespace")})
        .values("value")
        .distinct()
        .filter(namespace__isnull=False)
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [OpenShiftProjectPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift projects namespace,displays values related to the users access
        supported_query_params = ["search", "limit"]
        user_access = []
        error_message = {}
        # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        if request.user.admin:
            return super().list(request)
        elif request.user.access:
            user_access = request.user.access.get("openshift.project", {}).get("read", [])
        if user_access and user_access[0] == "*":
            return super().list(request)
        self.queryset = self.queryset.filter(namespace__in=user_access)
        return super().list(request)
