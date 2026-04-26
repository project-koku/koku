#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for StaticExchangeRate CRUD operations."""
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters import CharFilter
from django_filters import DateFilter
from django_filters import FilterSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework import viewsets
from rest_framework.response import Response

from api.common.permissions.cost_models_access import CostModelsAccessPermission
from cost_models.models import StaticExchangeRate
from cost_models.static_exchange_rate_serializer import StaticExchangeRateSerializer


class StaticExchangeRateFilter(FilterSet):
    """Filters for static exchange rate lookups."""

    base_currency = CharFilter(field_name="base_currency", lookup_expr="iexact")
    target_currency = CharFilter(field_name="target_currency", lookup_expr="iexact")
    start_date = DateFilter(field_name="end_date", lookup_expr="gte")
    end_date = DateFilter(field_name="start_date", lookup_expr="lte")

    class Meta:
        model = StaticExchangeRate
        fields = ["base_currency", "target_currency", "start_date", "end_date"]


class StaticExchangeRateViewSet(viewsets.ModelViewSet):
    """CRUD for static exchange rate pairs."""

    queryset = StaticExchangeRate.objects.all()
    serializer_class = StaticExchangeRateSerializer
    lookup_field = "uuid"
    permission_classes = (CostModelsAccessPermission,)
    http_method_names = ["get", "post", "put", "delete", "head"]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = StaticExchangeRateFilter

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
