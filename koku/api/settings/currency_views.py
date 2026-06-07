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
from api.currency.currencies import get_all_iso_currency_codes
from api.currency.currencies import get_currency_info
from api.currency.currencies import get_dynamic_rate_currencies
from api.currency.currencies import get_enabled_currency_codes
from api.currency.currencies import is_valid_iso_currency
from cost_models.models import EnabledCurrency
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.user_settings.models import UserSettings

LOG = logging.getLogger(__name__)


class CurrencySettingsView(APIView):
    """List all ISO 4217 currencies with enabled status and dynamic-rate availability.

    Supports ``?search=`` and ``?enabled=`` query params for filtering.
    """

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        enabled_codes = get_enabled_currency_codes()
        dynamic_codes = get_dynamic_rate_currencies()

        enabled_filter = request.query_params.get("enabled")
        if enabled_filter is not None and enabled_filter.lower() in ("true", "1"):
            sorted_codes = sorted(enabled_codes)
        elif enabled_filter is not None:
            all_codes = get_all_iso_currency_codes()
            sorted_codes = sorted(all_codes - enabled_codes)
        else:
            all_codes = get_all_iso_currency_codes()
            sorted_codes = sorted(enabled_codes) + sorted(all_codes - enabled_codes)

        result = []
        for code in sorted_codes:
            info = get_currency_info(code)
            info["enabled"] = code in enabled_codes
            info["has_dynamic_rate"] = code.lower() in dynamic_codes
            result.append(info)

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

        for user_setting in UserSettings.objects.filter(settings__currency=code):
            user_setting.settings["currency"] = KOKU_DEFAULT_CURRENCY
            user_setting.save(update_fields=["settings"])
            LOG.info(log_json(msg="Account currency reset to default", previous=code, new=KOKU_DEFAULT_CURRENCY))

        EnabledCurrency.objects.filter(currency_code=code).delete()
        LOG.info(log_json(msg="Currency disabled", currency=code))
        return Response(status=status.HTTP_204_NO_CONTENT)
