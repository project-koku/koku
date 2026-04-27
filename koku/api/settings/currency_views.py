#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for currency enablement."""
import logging

from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import log_json
from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.currency.currencies import _ISO_4217_CURRENCIES
from api.currency.currencies import get_currency_info
from api.currency.currencies import is_valid_iso_currency
from cost_models.models import EnabledCurrency

LOG = logging.getLogger(__name__)


class EnabledCurrencySerializer(serializers.Serializer):
    """Accepts a list of ISO 4217 currency codes to enable."""

    currencies = serializers.ListField(child=serializers.CharField(max_length=5), allow_empty=True)

    def validate_currencies(self, value):
        invalid = [code for code in value if not is_valid_iso_currency(code)]
        if invalid:
            raise serializers.ValidationError(f"Invalid ISO 4217 currency codes: {', '.join(invalid)}")
        return [code.upper() for code in value]


class EnabledCurrencyView(APIView):
    """Bulk-set enabled currencies for a tenant."""

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        serializer = EnabledCurrencySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        codes = serializer.validated_data["currencies"]
        with transaction.atomic():
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.bulk_create([EnabledCurrency(currency_code=code) for code in codes])

        LOG.info(log_json(msg="Enabled currencies updated", count=len(codes)))
        return Response(status=status.HTTP_204_NO_CONTENT)


class AllCurrencyView(APIView):
    """List all ISO 4217 currencies with an enabled flag."""

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
        result = []
        for code in sorted(_ISO_4217_CURRENCIES):
            info = get_currency_info(code)
            info["enabled"] = code in enabled_codes
            result.append(info)
        paginator = ListPaginator(result, request)
        return paginator.get_paginated_response(result)
