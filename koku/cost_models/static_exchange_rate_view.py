#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for StaticExchangeRate CRUD with MonthlyExchangeRate side effects."""
import logging

from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import log_json
from api.common.permissions.cost_models_access import CostModelsAccessPermission
from cost_models.models import StaticExchangeRate
from cost_models.monthly_exchange_rate_utils import remove_static_and_backfill_dynamic
from cost_models.static_exchange_rate_serializer import StaticExchangeRateSerializer
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types

LOG = logging.getLogger(__name__)


class StaticExchangeRateListView(APIView):
    """Create a new static exchange rate.

    POST - create a new static exchange rate
    """

    permission_classes = [CostModelsAccessPermission]

    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        serializer = StaticExchangeRateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        LOG.info(
            log_json(
                msg="Static exchange rate created",
                uuid=str(instance.uuid),
                pair=instance.name,
                start_date=str(instance.start_date),
                end_date=str(instance.end_date),
            )
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StaticExchangeRateDetailView(APIView):
    """Retrieve, update, and delete a single static exchange rate.

    PUT    - update an existing static exchange rate
    DELETE - delete a static exchange rate
    """

    permission_classes = [CostModelsAccessPermission]

    def _get_object(self, uuid):
        return get_object_or_404(StaticExchangeRate, pk=uuid)

    @method_decorator(never_cache)
    def put(self, request, *args, **kwargs):
        instance = self._get_object(kwargs["uuid"])
        serializer = StaticExchangeRateSerializer(instance, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        LOG.info(
            log_json(
                msg="Static exchange rate updated",
                uuid=str(instance.uuid),
                pair=instance.name,
            )
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @method_decorator(never_cache)
    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        instance = self._get_object(kwargs["uuid"])

        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        if instance.start_date < current_month_start:
            raise ValidationError("Rates with finalized months cannot be deleted.")

        remove_static_and_backfill_dynamic(
            instance.base_currency,
            instance.target_currency,
            instance.start_date,
            instance.end_date,
        )
        pair_name = instance.name
        instance.delete()
        invalidate_view_cache_for_tenant_and_all_source_types(request.user.customer.schema_name)
        LOG.info(
            log_json(
                msg="Static exchange rate deleted",
                pair=pair_name,
            )
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
