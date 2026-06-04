#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for currency list and enablement."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import log_json
from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.currency.currencies import get_currency_info
from api.currency.currencies import get_dynamic_rate_currencies
from api.currency.currencies import is_valid_iso_currency
from cost_models.models import EnabledCurrency

LOG = logging.getLogger(__name__)


class CurrencyListView(APIView):
    """List enabled currencies with name, symbol, and dynamic-rate availability.

    Supports ``?search=`` to filter by currency code.
    """

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
        dynamic_codes = get_dynamic_rate_currencies()

        result = [get_currency_info(code, dynamic_rate_codes=dynamic_codes) for code in sorted(enabled_codes)]

        search_term = request.query_params.get("search", "").strip().upper()
        if search_term:
            result = [c for c in result if search_term in c["code"]]

        return ListPaginator(result, request).paginated_response


class EnabledCurrencyView(APIView):
    """Enable or disable a single currency for a tenant.

    POST enables the currency; DELETE disables it.
    """

    permission_classes = [SettingsAccessPermission]

    def _validate_code(self, code):
        code = code.upper()
        if not is_valid_iso_currency(code):
            raise ValidationError({"code": f"Invalid ISO 4217 currency code: {code}"})
        return code

    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        code = self._validate_code(kwargs["code"])
        EnabledCurrency.objects.get_or_create(currency_code=code)
        LOG.info(log_json(msg="Currency enabled", currency=code))
        return Response(status=status.HTTP_200_OK)

    @method_decorator(never_cache)
    def delete(self, request, *args, **kwargs):
        code = self._validate_code(kwargs["code"])
        EnabledCurrency.objects.filter(currency_code=code).delete()
        LOG.info(log_json(msg="Currency disabled", currency=code))
        return Response(status=status.HTTP_204_NO_CONTENT)
