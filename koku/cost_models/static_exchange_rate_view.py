#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for StaticExchangeRate CRUD operations."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework import viewsets
from rest_framework.response import Response

from api.common.permissions.cost_models_access import CostModelsAccessPermission
from cost_models.models import StaticExchangeRate
from cost_models.static_exchange_rate_serializer import StaticExchangeRateSerializer

LOG = logging.getLogger(__name__)


class StaticExchangeRateViewSet(viewsets.ModelViewSet):
    """CRUD for static exchange rate pairs."""

    queryset = StaticExchangeRate.objects.all()
    serializer_class = StaticExchangeRateSerializer
    lookup_field = "uuid"
    permission_classes = (CostModelsAccessPermission,)
    http_method_names = ["get", "post", "put", "delete", "head"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if base := params.get("base_currency"):
            qs = qs.filter(base_currency=base.upper())
        if target := params.get("target_currency"):
            qs = qs.filter(target_currency=target.upper())
        if start_date := params.get("start_date"):
            qs = qs.filter(end_date__gte=start_date)
        if end_date := params.get("end_date"):
            qs = qs.filter(start_date__lte=end_date)
        return qs

    @method_decorator(never_cache)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @method_decorator(never_cache)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @method_decorator(never_cache)
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @method_decorator(never_cache)
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @method_decorator(never_cache)
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        serializer.delete(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
