#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for currency enablement and available currencies."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import log_json
from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from cost_models.models import EnabledCurrency
from cost_models.models import StaticExchangeRate

LOG = logging.getLogger(__name__)


class EnabledCurrencyItemSerializer(serializers.Serializer):
    currency_code = serializers.CharField(max_length=5)
    enabled = serializers.BooleanField()


class EnabledCurrencyUpdateSerializer(serializers.Serializer):
    currencies = EnabledCurrencyItemSerializer(many=True)


class EnabledCurrencyView(APIView):
    """List and update enabled/disabled currencies for a tenant."""

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        currencies = EnabledCurrency.objects.all().values("currency_code", "enabled")
        data = list(currencies)
        paginator = ListPaginator(data, request)
        return paginator.get_paginated_response(data)

    @method_decorator(never_cache)
    def put(self, request, *args, **kwargs):
        serializer = EnabledCurrencyUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        for item in serializer.validated_data["currencies"]:
            EnabledCurrency.objects.update_or_create(
                currency_code=item["currency_code"].upper(),
                defaults={"enabled": item["enabled"]},
            )

        LOG.info(
            log_json(
                msg="Enabled currencies updated",
                count=len(serializer.validated_data["currencies"]),
            )
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AvailableCurrencyView(APIView):
    """Returns currencies visible in the target currency dropdown."""

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        enabled_codes = set(EnabledCurrency.objects.filter(enabled=True).values_list("currency_code", flat=True))

        static_bases = set(StaticExchangeRate.objects.values_list("base_currency", flat=True))
        static_targets = set(StaticExchangeRate.objects.values_list("target_currency", flat=True))
        static_currencies = static_bases | static_targets

        data = []
        for code in sorted(enabled_codes | static_currencies):
            in_dynamic = code in enabled_codes
            in_static = code in static_currencies
            if in_dynamic and in_static:
                source = "both"
            elif in_static:
                source = "static"
            else:
                source = "dynamic"
            data.append({"currency_code": code, "source": source})

        paginator = ListPaginator(data, request)
        return paginator.get_paginated_response(data)
