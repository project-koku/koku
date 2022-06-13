#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from decimal import Decimal

from api.currency.models import ExchangeRates

# from api.currency.models import ExchangeRateDictionary

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
    return Decimal(exchange_rates[target_currency] / exchange_rates[base_currency])


def build_exchange_dictionary(rates, row=0, exchange_rates={}):
    """Build the exchange rates dictionary"""
    current_currency = rates.get().values()
    print("currency : ", current_currency)
    # currency_dict = {}
    # for code, rate in rates:
    #     if current_currency == 'USD':
    #         currency_dict[current_currency].append({code : rate})
    #     else:
    #         if code == 'USD':
    #             currency_dict[current_currency].append({code : 1/rate})
    #         else:
    #             currency_dict[current_currency].append({code : _get_exchange_rate(current_currency, rate)})
    # exchange_rates.append(currency_dict)
    # row += 1
    # if rates[row]:
    #     build_exchange_dictionary(rates, row, exchange_rates)

    # print("DICTIONARY: ", exchange_rates)
    # ExchangeRateDictionary.currency_exchange_dictionary = exchange_rates
    # ExchangeRateDictionary.save()
