#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Price Lists."""
import logging

from django.db.models import Count
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters import BooleanFilter
from django_filters import CharFilter
from django_filters import UUIDFilter
from django_filters.rest_framework import DjangoFilterBackend
from querystring_parser import parser
from rest_framework import serializers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from api.common.permissions.cost_models_access import CostModelsAccessPermission
from api.report.constants import URL_ENCODED_SAFE
from api.settings.utils import ListFilter
from api.settings.utils import SettingsFilter
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.price_list_manager import PriceListException
from cost_models.price_list_manager import PriceListManager
from cost_models.price_list_serializer import PriceListSerializer

LOG = logging.getLogger(__name__)

VALID_PARAMS = {"filter", "order_by", "limit", "offset"}


class PriceListFilter(SettingsFilter):
    """Price list custom filters."""

    name = ListFilter(field_name="name", lookup_expr="icontains")
    uuid = UUIDFilter(field_name="uuid")
    enabled = BooleanFilter(field_name="enabled")
    currency = CharFilter(field_name="currency", lookup_expr="iexact")

    def filter_queryset(self, queryset):
        """Validate top-level params before delegating to SettingsFilter."""
        if self.request:
            query_params = parser.parse(self.request.query_params.urlencode(safe=URL_ENCODED_SAFE))
            invalid = set(query_params.keys()) - VALID_PARAMS
            if invalid:
                raise ValidationError({invalid.pop(): "Unsupported parameter or invalid value"})
        return super().filter_queryset(queryset)

    class Meta:
        model = PriceList
        fields = ["name", "uuid", "enabled", "currency"]
        default_ordering = ["name"]


class PriceListViewSet(viewsets.ModelViewSet):
    """PriceList View.

    A viewset that provides default `create()`, `destroy`, `retrieve()`,
    and `list()` actions.
    """

    serializer_class = PriceListSerializer
    permission_classes = (CostModelsAccessPermission,)
    lookup_field = "uuid"
    filter_backends = (DjangoFilterBackend,)
    filterset_class = PriceListFilter
    http_method_names = ["get", "post", "head", "delete", "put"]

    def get_queryset(self):
        """Get queryset with assigned cost model count annotation and prefetch."""
        return PriceList.objects.annotate(assigned_cost_model_count=Count("cost_model_maps")).prefetch_related(
            "cost_model_maps__cost_model"
        )

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

    @method_decorator(never_cache)
    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, uuid=None):
        """Duplicate a price list."""
        price_list = self.get_object()
        serializer = self.get_serializer(price_list)
        new_price_list = serializer.duplicate(price_list)
        return Response(self.get_serializer(new_price_list).data, status=status.HTTP_201_CREATED)
