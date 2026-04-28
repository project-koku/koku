#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for currency enablement."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import log_json
from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.currency.currencies import _ISO_4217_CURRENCIES
from api.currency.currencies import get_currency_info
from api.currency.currencies import is_valid_iso_currency
from api.settings.serializers import EnabledCurrencySerializer
from cost_models.models import EnabledCurrency

LOG = logging.getLogger(__name__)


class EnabledCurrencyView(APIView):
    """Toggle a single currency's enabled state for a tenant."""

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def put(self, request, *args, **kwargs):
        code = kwargs["code"].upper()
        if not is_valid_iso_currency(code):
            return Response({"code": [f"Invalid ISO 4217 currency code: {code}"]}, status=status.HTTP_400_BAD_REQUEST)

        serializer = EnabledCurrencySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["enabled"]:
            EnabledCurrency.objects.get_or_create(currency_code=code)
            LOG.info(log_json(msg="Currency enabled", currency=code))
        else:
            EnabledCurrency.objects.filter(currency_code=code).delete()
            LOG.info(log_json(msg="Currency disabled", currency=code))

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
