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
from api.currency.currencies import CURRENCIES
from api.currency.models import ExchangeRateDictionary


@api_view(("GET",))
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def get_currency(request):
    """Get Currency Data.

    This method is responsible for passing request data to the reporting APIs.

    Args:
        request (Request): The HTTP request object

    Returns:
        (Response): The report in a Response object

    """
    return ListPaginator(CURRENCIES, request).paginated_response


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
