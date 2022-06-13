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
from rest_framework.settings import api_settings

from api.common.pagination import ListPaginator
from api.currency.currencies import CURRENCIES
from api.currency.models import ExchangeRateDictionary
from api.currency.utils import exchange_dictionary

# from api.currency.models import ExchangeRates
# from api.currency.utils import build_exchange_dictionary


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
    rates = {"USD": 1, "AUD": 1.44, "JPY": 132.06, "EUR": 0.96}
    exchange_dictionary(rates)
    exchange_rates = ExchangeRateDictionary.objects.all()
    return (ListPaginator(exchange_rates, request)).paginated_response
