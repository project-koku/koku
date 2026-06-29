#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for StaticExchangeRate CRUD."""
import logging

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
from cost_models.static_exchange_rate_serializer import StaticExchangeRateSerializer

LOG = logging.getLogger(__name__)


class StaticExchangeRateListView(APIView):
    """Create a new static exchange rate.

    POST - create a new static exchange rate
    """

    permission_classes = [CostModelsAccessPermission]

    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        serializer = StaticExchangeRateSerializer(data=request.data)
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
        return Response(StaticExchangeRateSerializer(instance).data, status=status.HTTP_201_CREATED)


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

        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        if instance.start_date < current_month_start:
            raise ValidationError({"error": "Cannot edit rates for past months."})

        serializer = StaticExchangeRateSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        LOG.info(
            log_json(
                msg="Static exchange rate updated",
                uuid=str(instance.uuid),
                pair=instance.name,
            )
        )
        return Response(StaticExchangeRateSerializer(instance).data, status=status.HTTP_200_OK)

    @method_decorator(never_cache)
    def delete(self, request, *args, **kwargs):
        instance = self._get_object(kwargs["uuid"])

        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        if instance.start_date < current_month_start:
            raise ValidationError({"error": "Cannot delete rates for past months."})

        LOG.info(
            log_json(
                msg="Static exchange rate deleted",
                uuid=str(instance.uuid),
                pair=instance.name,
            )
        )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
