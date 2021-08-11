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
        # Reads the users values for Openshift projects namespace,displays values related to the users access"""
        user_access = []
        if request.user.admin:
            return super().list(request)
        elif request.user.access:
            user_access = request.user.access.get("openshift.project", {}).get("read", [])
        self.queryset = self.queryset.values("value").filter(namespace__in=user_access)
        return super().list(request)
