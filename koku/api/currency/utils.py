#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from decimal import Decimal

from api.currency.models import ExchangeRateDictionary

LOG = logging.getLogger(__name__)


def build_exchange_dictionary(rates, index=0, exchange_rates={}):
    """Build the exchange rates dictionary"""
    currency_dict = {}
    base_currency_list = list(rates.keys())
    base_currency = base_currency_list[index]
    for code in rates:
        if base_currency == "USD":
            value = Decimal(rates[code])
        else:
            if code == "USD":
                value = Decimal(1 / rates[base_currency])
            else:
                value = Decimal(rates[code] / rates[base_currency])
        currency_dict[code] = value
    exchange_rates[base_currency] = currency_dict
    index += 1
    if index < len(base_currency_list):
        build_exchange_dictionary(rates, index, exchange_rates)

    return exchange_rates


def exchange_dictionary(rates):
    """Posts exchange rates dictionary to DB"""
    exchange_data = build_exchange_dictionary(rates)
    current_data = ExchangeRateDictionary.objects.all().first()
    if not current_data:
        ExchangeRateDictionary.objects.create(currency_exchange_dictionary=exchange_data)
    else:
        current_data.currency_exchange_dictionary = exchange_data
        current_data.save()
