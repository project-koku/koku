#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for StaticExchangeRate CRUD operations."""
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework import viewsets

from api.common import log_json
from api.common.permissions.cost_models_access import CostModelsAccessPermission
from cost_models.models import StaticExchangeRate
from cost_models.static_exchange_rate_serializer import StaticExchangeRateSerializer
from cost_models.static_exchange_rate_utils import remove_static_and_backfill_dynamic
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types

LOG = logging.getLogger(__name__)


class StaticExchangeRateViewSet(viewsets.ModelViewSet):
    """CRUD for static exchange rate pairs."""

    queryset = StaticExchangeRate.objects.all()
    serializer_class = StaticExchangeRateSerializer
    lookup_field = "uuid"
    permission_classes = (CostModelsAccessPermission,)
    http_method_names = ["post", "put", "delete", "head"]

    @transaction.atomic
    def perform_destroy(self, instance):
        current_month_start = timezone.now().date().replace(day=1)
        if instance.start_date < current_month_start:
            raise serializers.ValidationError(
                "Cannot delete exchange rates that cover past billing periods. "
                "Only rates starting in the current month or later may be deleted."
            )
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
