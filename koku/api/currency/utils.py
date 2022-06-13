#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

from api.currency.models import ExchangeRateDictionary
from api.currency.models import ExchangeRates

# from decimal import Decimal

LOG = logging.getLogger(__name__)


def _get_exchange_rate(base_currency, target_currency):
    """Look up the exchange rate for the target currency."""
    exchange_rates = {}
    for currency in [target_currency, base_currency]:
        try:
            exchange_rate = ExchangeRates.objects.get(currency_type=currency.lower())
            exchange_rates[currency] = exchange_rate.exchange_rate
        except Exception as e:
            LOG.error(e)
            return 1
    return float(exchange_rates[target_currency] / exchange_rates[base_currency])


def build_exchange_dictionary(rates, index=0, exchange_rates={}):
    """Build the exchange rates dictionary"""
    currency_dict = {}
    base_currency_list = list(rates.keys())
    base_currency = base_currency_list[index]
    for code in rates:
        if code == "USD":
            currency_dict[code] = rates[code]
        else:
            if code == "USD":
                currency_dict[code] = 1 / rates[code]
            else:
                currency_dict[code] = _get_exchange_rate(base_currency, code)
    exchange_rates[base_currency] = currency_dict
    print("\n\nEXCHANGE: ", exchange_rates)
    index += 1
    if index < len(base_currency_list):
        build_exchange_dictionary(rates, index, exchange_rates)

    return exchange_rates


def exchange_dictionary(rates):
    """Posts exchange rates dictionary to DB"""
    try:
        exchange_rate_dict = ExchangeRateDictionary.objects.all().first()
        LOG.info("Updating currency Exchange rate mapping dict")
    except ExchangeRateDictionary.DoesNotExist:
        LOG.info("Creating the exchange rate mapping dict")
        exchange_rate_dict = ExchangeRates()
    exchange_rate_dict.exchange_rate = build_exchange_dictionary(rates)
    exchange_rate_dict.save()
    # print("RATES", rates)
    # exchange_dictionary = build_exchange_dictionary(rates)
    # print("\n\nBRUH: ", exchange_dictionary)
    # exchange_dict = ExchangeRateDictionary.objects.all().first()
    # if not exchange_dict:
    #     ExchangeRateDictionary.objects.create(currency_exchange_dictionary=exchange_dictionary)
    # else:
    #     exchange_dict = ExchangeRateDictionary(currency_exchange_dictionary = exchange_dictionary)
    #     exchange_dict.save(currency_exchange_dictionary = exchange_dictionary)
