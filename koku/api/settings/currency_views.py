#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for currency list and enablement."""
import logging
from collections import defaultdict

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
from api.currency.currencies import get_enabled_currency_codes
from api.currency.currencies import is_valid_iso_currency
from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import EnabledCurrency
from cost_models.models import PriceList
from cost_models.models import StaticExchangeRate
from cost_models.monthly_exchange_rate_utils import populate_dynamic_monthly_rates
from cost_models.monthly_exchange_rate_utils import remove_monthly_rates
from cost_models.static_exchange_rate_serializer import StaticExchangeRateSerializer
from koku.cache import build_enabled_currency_codes_key
from koku.cache import delete_value_from_cache
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.provider.aws.models import AWSCostSummaryP
from reporting.provider.azure.models import AzureCostSummaryP
from reporting.provider.gcp.models import GCPCostSummaryP
from reporting.user_settings.models import UserSettings

LOG = logging.getLogger(__name__)


def _get_cloud_providers_using_currency(code, customer):
    """Return cloud providers whose billing data uses ``code`` as a base currency."""
    if not customer or not customer.pk:
        return []
    aws_uuids = AWSCostSummaryP.objects.filter(currency_code=code).values_list("source_uuid", flat=True).distinct()
    azure_uuids = AzureCostSummaryP.objects.filter(currency=code).values_list("source_uuid", flat=True).distinct()
    gcp_uuids = GCPCostSummaryP.objects.filter(currency=code).values_list("source_uuid", flat=True).distinct()

    return list(
        Provider.objects.filter(
            Q(uuid__in=aws_uuids) | Q(uuid__in=azure_uuids) | Q(uuid__in=gcp_uuids),
            customer=customer,
        ).values("uuid", "name", "type")
    )


class CurrencySettingsView(APIView):
    """List all ISO 4217 currencies with enabled status and dynamic-rate availability.

    Supports ``?search=`` and ``?enabled=`` query params for filtering.
    """

    permission_classes = [SettingsAccessPermission]

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        enabled_codes = get_enabled_currency_codes()
        dynamic_codes = get_dynamic_rate_currencies()

        static_rates = StaticExchangeRate.objects.all()
        serialized_rates = StaticExchangeRateSerializer(static_rates, many=True).data
        rates_by_base = defaultdict(list)
        for rate in serialized_rates:
            code = rate["base_currency"]
            rates_by_base[code].append(rate)

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
            info["static_rates"] = rates_by_base.get(code, [])
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
        _, created = EnabledCurrency.objects.get_or_create(currency_code=code)
        if created:
            populate_dynamic_monthly_rates(code=code)
            schema_name = request.user.customer.schema_name
            invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
            delete_value_from_cache(build_enabled_currency_codes_key(schema_name))
        LOG.info(log_json(msg="Currency enabled", currency=code))
        return Response(status=status.HTTP_200_OK)

    @method_decorator(never_cache)
    def delete(self, request, *args, **kwargs):
        code = self._validate_code(kwargs["code"])

        if not EnabledCurrency.objects.filter(currency_code=code).exists():
            return Response(status=status.HTTP_204_NO_CONTENT)

        if EnabledCurrency.objects.count() == 1:
            raise ValidationError({"error": "At least one currency must be enabled."})

        reasons = []

        if code == KOKU_DEFAULT_CURRENCY:
            reasons.append("it is the system default currency")

        account_settings = UserSettings.objects.first()
        if account_settings and account_settings.settings.get("currency") == code:
            reasons.append("it is the account default currency")

        affected_cloud_providers = _get_cloud_providers_using_currency(code, request.user.customer)
        if affected_cloud_providers:
            reasons.append(f"it is currently used by {len(affected_cloud_providers)} cloud provider source(s)")

        affected_cost_models = list(CostModel.objects.filter(currency=code).values("uuid", "name"))
        if affected_cost_models:
            reasons.append(f"it is used by {len(affected_cost_models)} cost model(s)")

        affected_price_lists = list(PriceList.objects.filter(currency=code).values("uuid", "name"))
        if affected_price_lists:
            reasons.append(f"it is used by {len(affected_price_lists)} price list(s)")

        if reasons:
            detail = f"Cannot disable {code} because {'; '.join(reasons)}."
            LOG.info(
                log_json(
                    msg="Currency disable blocked",
                    currency=code,
                    reasons=reasons,
                    affected_cloud_providers=affected_cloud_providers,
                    affected_cost_models=affected_cost_models,
                    affected_price_lists=affected_price_lists,
                )
            )
            return Response(
                {
                    "errors": [
                        {
                            "detail": detail,
                            "source": "currency",
                            "status": status.HTTP_400_BAD_REQUEST,
                        }
                    ],
                    "affected_cloud_providers": affected_cloud_providers,
                    "affected_cost_models": affected_cost_models,
                    "affected_price_lists": affected_price_lists,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        EnabledCurrency.objects.filter(currency_code=code).delete()
        remove_monthly_rates(code=code)
        schema_name = request.user.customer.schema_name
        invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
        delete_value_from_cache(build_enabled_currency_codes_key(schema_name))
        LOG.info(log_json(msg="Currency disabled", currency=code))

        return Response(status=status.HTTP_204_NO_CONTENT)
