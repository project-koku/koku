#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Price Lists."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters import CharFilter
from django_filters import FilterSet
from django_filters import UUIDFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from api.common.permissions.cost_models_access import CostModelsAccessPermission
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.price_list_manager import PriceListException
from cost_models.price_list_manager import PriceListManager
from cost_models.price_list_serializer import PriceListSerializer

LOG = logging.getLogger(__name__)


class PriceListFilter(FilterSet):
    """Price list custom filters."""

    name = CharFilter(field_name="name", lookup_expr="icontains")
    uuid = UUIDFilter(field_name="uuid")
    enabled = CharFilter(field_name="enabled")

    class Meta:
        model = PriceList
        fields = ["name", "uuid", "enabled"]


class PriceListViewSet(viewsets.ModelViewSet):
    """PriceList View.

    A viewset that provides default `create()`, `destroy`, `retrieve()`,
    and `list()` actions.
    """

    queryset = PriceList.objects.all()
    serializer_class = PriceListSerializer
    permission_classes = (CostModelsAccessPermission,)
    lookup_field = "uuid"
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PriceListFilter
    ordering_fields = ("name", "effective_start_date", "updated_timestamp")
    ordering = ("name",)
    http_method_names = ["get", "post", "head", "delete", "put"]

    @method_decorator(never_cache)
    def create(self, request, *args, **kwargs):
        """Create a price list."""
        return super().create(request=request, args=args, kwargs=kwargs)

    @method_decorator(never_cache)
    def list(self, request, *args, **kwargs):
        """List price lists."""
        return super().list(request=request, args=args, kwargs=kwargs)

    @method_decorator(never_cache)
    def retrieve(self, request, *args, **kwargs):
        """Get a price list."""
        return super().retrieve(request=request, args=args, kwargs=kwargs)

    @method_decorator(never_cache)
    def destroy(self, request, *args, **kwargs):
        """Delete a price list."""
        return super().destroy(request=request, args=args, kwargs=kwargs)

    def perform_destroy(self, instance):
        """Delete via the manager (checks for cost model assignments)."""
        try:
            manager = PriceListManager(instance.uuid)
            manager.delete()
        except PriceListException as error:
            raise serializers.ValidationError(str(error))

    @method_decorator(never_cache)
    def update(self, request, *args, **kwargs):
        """Update a price list."""
        return super().update(request=request, args=args, kwargs=kwargs)

    @method_decorator(never_cache)
    @action(detail=True, methods=["get"], url_path="affected-cost-models")
    def affected_cost_models(self, request, uuid=None):
        """Return cost models that use this price list."""
        price_list = self.get_object()
        maps = PriceListCostModelMap.objects.filter(price_list=price_list).select_related("cost_model")
        result = [
            {
                "uuid": str(m.cost_model.uuid),
                "name": m.cost_model.name,
                "priority": m.priority,
            }
            for m in maps
        ]
        return Response(result)
