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

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.openshift_access import OpenShiftNodePermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.ocp.models import OCPCostSummaryByNode


class OCPNodesView(generics.ListAPIView):
    """API GET list view for Openshift nodes."""

    queryset = OCPCostSummaryByNode.objects.annotate(**{"value": F("node")}).values("value").distinct()
    serializer_class = ResourceTypeSerializer
    permission_classes = [OpenShiftNodePermission]
    filter_backends = [filters.OrderingFilter]
    ordering = ["value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift nodes and displays values that the user has access too
        if request.user.admin:
            return super().list(request)
        elif request.user.access:
            user_access = request.user.access.get("openshift.node", {}).get("read", [])
        else:
            user_access = []
        self.queryset = self.queryset.values("value").filter(node__in=user_access)
        return super().list(request)
