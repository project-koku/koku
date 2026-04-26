#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for StaticExchangeRate CRUD operations."""
import logging

from django.db import transaction
from django_filters import CharFilter
from django_filters import DateFilter
from django_filters import FilterSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets

from api.common import log_json
from api.common.permissions.cost_models_access import CostModelsAccessPermission
from cost_models.models import StaticExchangeRate
from cost_models.static_exchange_rate_serializer import StaticExchangeRateSerializer
from cost_models.static_exchange_rate_utils import remove_static_and_backfill_dynamic
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types

LOG = logging.getLogger(__name__)


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

    @transaction.atomic
    def perform_destroy(self, instance):
        remove_static_and_backfill_dynamic(
            instance.base_currency,
            instance.target_currency,
            instance.start_date,
            instance.end_date,
        )
        pair_name = instance.name
        instance.delete()
        invalidate_view_cache_for_tenant_and_all_source_types(self.request.user.customer.schema_name)
        LOG.info(log_json(msg="Static exchange rate deleted", pair=pair_name))
