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
from api.currency.models import ExchangeRateDictionary
from cost_models.models import EnabledCurrency


@api_view(("GET",))
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def get_currency(request):
    """Get available currencies.

    Returns currencies that have been enabled by an administrator via
    the EnabledCurrency table.  Display name is resolved via pycountry
    at discovery time and stored on the row.
    """
    currencies = EnabledCurrency.objects.filter(enabled=True).values("currency_code", "currency_name")
    available = [
        {"code": c["currency_code"], "name": c["currency_name"] or c["currency_code"]}
        for c in currencies.order_by("currency_code")
    ]
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
