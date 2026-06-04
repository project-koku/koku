#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Currency."""
from rest_framework import permissions
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.common.pagination import ListPaginator
from api.currency.currencies import get_currency_info
from api.currency.currencies import get_dynamic_rate_currencies
from api.currency.models import ExchangeRateDictionary
from cost_models.models import EnabledCurrency


@api_view(("GET",))
@permission_classes((permissions.IsAuthenticated,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def get_currency(request):
    """Get available currencies.

    Returns currencies that have been enabled by an administrator via
    the EnabledCurrency table.  Name, symbol, and description are
    computed at response time via babel.
    """
    enabled_codes = EnabledCurrency.objects.values_list("currency_code", flat=True)
    dynamic_codes = get_dynamic_rate_currencies()
    available = [get_currency_info(code, dynamic_rate_codes=dynamic_codes) for code in sorted(enabled_codes)]
    return ListPaginator(available, request).paginated_response


@api_view(("GET",))
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def get_exchange_rates(request):
    """Get the currency exchange rates between all currencies"""
    exchange_rates = ExchangeRateDictionary.objects.all().first()
    if not exchange_rates:
        from masu.celery.tasks import get_daily_currency_rates

        get_daily_currency_rates()
        exchange_rates = ExchangeRateDictionary.objects.all().first()
    return Response(exchange_rates.currency_exchange_dictionary)
