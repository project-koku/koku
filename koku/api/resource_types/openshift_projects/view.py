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
from api.common.permissions.resource_type_access import ResourceTypeAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.ocp.models import OCPCostSummaryByProject


class OCPProjectsView(generics.ListAPIView):
    """API GET list view for Openshift projects."""

    queryset = OCPCostSummaryByProject.objects.annotate(**{"value": F("namespace")}).values("value").distinct()
    serializer_class = ResourceTypeSerializer
    permission_classes = [ResourceTypeAccessPermission]
    filter_backends = [filters.OrderingFilter]
    ordering = ["value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        return super().list(request)
