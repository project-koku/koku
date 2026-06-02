#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for currency enablement."""
import logging

from django.db.models import Q
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
from api.currency.currencies import is_valid_iso_currency
from api.currency.utils import get_missing_rate_warning
from api.utils import DateHelper
from cost_models.models import EnabledCurrency
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType

LOG = logging.getLogger(__name__)


class EnabledCurrencyView(APIView):
    """Enable or disable a single currency for a tenant.

    POST enables the currency; DELETE disables it. No request body required.
    """

    permission_classes = [SettingsAccessPermission]

    def _validate_code(self, code):
        code = code.upper()
        if not is_valid_iso_currency(code):
            raise ValidationError({"code": f"Invalid ISO 4217 currency code: {code}"})
        return code

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        if "code" in kwargs:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

        enabled_codes = set(EnabledCurrency.objects.values_list("currency_code", flat=True))
        dynamic_codes = get_dynamic_rate_currencies()

        search_term = request.query_params.get("search", "").strip().lower()
        all_codes = get_all_iso_currency_codes()
        result = []
        for code in all_codes:
            info = get_currency_info(code, dynamic_rate_codes=dynamic_codes)
            if search_term and search_term not in info["code"].lower() and search_term not in info["name"].lower():
                continue
            info["enabled"] = code in enabled_codes
            result.append(info)

        enabled_filter = request.query_params.get("enabled")
        if enabled_filter is not None:
            show_enabled = enabled_filter.lower() in ("true", "1")
            result = [currency for currency in result if currency["enabled"] is show_enabled]

        result.sort(key=lambda currency: (not currency["enabled"], currency["code"]))

        return ListPaginator(result, request).paginated_response

    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        code = self._validate_code(kwargs["code"])
        EnabledCurrency.objects.get_or_create(currency_code=code)
        LOG.info(log_json(msg="Currency enabled", currency=code))

        warning = get_missing_rate_warning(code)
        if warning:
            LOG.warning(log_json(msg="Currency enabled with warning", currency=code, warning=warning))
        return Response({"warning": warning}, status=status.HTTP_200_OK)

    @method_decorator(never_cache)
    def delete(self, request, *args, **kwargs):
        code = self._validate_code(kwargs["code"])
        EnabledCurrency.objects.filter(currency_code=code).delete()
        current_month = DateHelper().this_month_start.date()
        deleted_count, _ = MonthlyExchangeRate.objects.filter(
            Q(base_currency=code) | Q(target_currency=code),
            rate_type=RateType.DYNAMIC,
            effective_date=current_month,
        ).delete()
        if deleted_count:
            LOG.info(
                log_json(msg="Cleaned up dynamic rates for disabled currency", currency=code, deleted=deleted_count)
            )
        LOG.info(log_json(msg="Currency disabled", currency=code))
        return Response(status=status.HTTP_204_NO_CONTENT)
