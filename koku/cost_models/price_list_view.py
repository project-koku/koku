#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Price Lists."""
import copy
import logging

from django.db.models import Count
from django.shortcuts import get_object_or_404
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

from api.common.pagination import ListPaginator
from api.common.permissions.cost_models_access import CostModelsAccessPermission
from api.metrics import constants as metric_constants
from api.report.constants import URL_ENCODED_SAFE
from api.settings.utils import ListFilter
from api.settings.utils import SettingsFilter
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from cost_models.price_list_manager import PriceListException
from cost_models.price_list_manager import PriceListManager
from cost_models.price_list_serializer import PriceListSerializer
from cost_models.rate_sync import sync_rate_table

LOG = logging.getLogger(__name__)

VALID_PARAMS = {"filter", "order_by", "limit", "offset"}


class RateFilter(SettingsFilter):
    """Filter for Rate objects on the rates sub-endpoint."""

    name = ListFilter(field_name="custom_name", lookup_expr="icontains")
    metric_type = ListFilter(field_name="metric_type", lookup_expr="iexact")
    measurement = ListFilter(field_name="metric", lookup_expr="iexact", method="filter_measurement")
    cost_type = ListFilter(field_name="cost_type", lookup_expr="iexact")

    def filter_measurement(self, queryset, name, value):
        """Reverse-map measurement labels to metric names and filter."""
        if not value:
            return queryset
        schema = getattr(getattr(getattr(self.request, "user", None), "customer", None), "schema_name", None)
        metrics_map = metric_constants.get_cost_model_metrics_map(schema=schema)
        matching_metrics = set()
        for metric_name, entry in metrics_map.items():
            label = entry.get("label_measurement", "").lower()
            if any(v.lower() in label for v in value):
                matching_metrics.add(metric_name)
        if not matching_metrics:
            return queryset.none()
        return queryset.filter(metric__in=matching_metrics)

    class Meta:
        model = Rate
        fields = ["name", "metric_type", "measurement", "cost_type"]
        default_ordering = ["custom_name"]


class PriceListFilter(SettingsFilter):
    """Price list custom filters."""

    name = ListFilter(field_name="name", lookup_expr="icontains")
    uuid = UUIDFilter(field_name="uuid")
    enabled = BooleanFilter(field_name="enabled")
    currency = CharFilter(field_name="currency", lookup_expr="iexact")
    cost_model = ListFilter(field_name="cost_model_maps__cost_model__uuid", lookup_expr="exact")

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
        fields = ["name", "uuid", "enabled", "currency", "cost_model"]
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
        return (
            PriceList.objects.annotate(assigned_cost_model_count=Count("cost_model_maps", distinct=True))
            .prefetch_related("cost_model_maps__cost_model")
            .distinct()
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

    @method_decorator(never_cache)
    @action(detail=True, methods=["get"], url_path="rates")
    def rates(self, request, uuid=None):
        """Return filterable, paginated rates for a price list."""
        price_list = get_object_or_404(self.get_queryset(), uuid=uuid)
        self.check_object_permissions(request, price_list)
        self._ensure_rate_sync(price_list)

        rate_qs = Rate.objects.filter(price_list=price_list)
        rate_filter = RateFilter(data=request.query_params, queryset=rate_qs, request=request)
        filtered_qs = rate_filter.qs

        schema = getattr(getattr(request.user, "customer", None), "schema_name", None)
        rate_data = self._build_rate_response(price_list, filtered_qs, schema)

        paginator = ListPaginator(rate_data, request)
        return paginator.paginated_response

    def _ensure_rate_sync(self, price_list):
        """Trigger sync_rate_table if JSON entries lack rate_id (migration 0013 gap)."""
        if not price_list.rates:
            return
        if any("rate_id" not in entry for entry in price_list.rates):
            LOG.info("Lazy sync triggered for PriceList %s: rate_id missing from JSON", price_list.uuid)
            try:
                sync_rate_table(price_list, copy.deepcopy(price_list.rates))
            except (ValueError, Exception):
                LOG.exception("Lazy sync failed for PriceList %s", price_list.uuid)
                return
            price_list.refresh_from_db()

    def _build_rate_response(self, price_list, filtered_qs, schema=None):
        """Cross-reference filtered Rate rows with JSON and enrich with metric labels."""
        metrics_map = metric_constants.get_cost_model_metrics_map(schema=schema)
        json_by_rate_id = {}
        for entry in price_list.rates or []:
            rid = entry.get("rate_id")
            if rid:
                json_by_rate_id[rid] = entry

        result = []
        for rate_obj in filtered_qs:
            rate_id_str = str(rate_obj.uuid)
            json_entry = json_by_rate_id.get(rate_id_str, {})
            metric_name = rate_obj.metric
            metric_info = metrics_map.get(metric_name, {})
            rate_dict = {
                "rate_id": rate_id_str,
                "custom_name": rate_obj.custom_name,
                "description": rate_obj.description,
                "metric": {
                    "name": metric_name,
                    "label_metric": metric_info.get("label_metric", ""),
                    "label_measurement": metric_info.get("label_measurement", ""),
                    "label_measurement_unit": metric_info.get("label_measurement_unit", ""),
                },
                "metric_type": rate_obj.metric_type,
                "cost_type": rate_obj.cost_type,
                "default_rate": str(rate_obj.default_rate) if rate_obj.default_rate is not None else None,
            }
            if json_entry.get("tiered_rates"):
                rate_dict["tiered_rates"] = json_entry["tiered_rates"]
            if json_entry.get("tag_rates"):
                rate_dict["tag_rates"] = json_entry["tag_rates"]
            result.append(rate_dict)
        return result
