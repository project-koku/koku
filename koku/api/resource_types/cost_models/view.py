#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Resource Types Cost Model."""
from django.db.models import CharField
from django.db.models import Value as V
from django.db.models.functions import Concat
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.resource_type_access import ResourceTypeAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from cost_models.models import CostModel


class CostModelResourceTypesView(generics.ListAPIView):
    """API GET for resource types cost model view."""

    queryset = (
        CostModel.objects.all()
        .annotate(value=Concat("uuid", V(" ("), "name", V(")"), output_field=CharField()))
        .values("value")
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [ResourceTypeAccessPermission]
    filter_backends = [filters.OrderingFilter]
    ordering = ["value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        return super().list(request)
