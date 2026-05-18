#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from decimal import Decimal

from django.conf import settings

from api.currency.models import ExchangeRateDictionary


def build_exchange_dictionary(rates):
    """Build the exchange rates dictionary"""
    exchanged_rates = {}
    for currency_key, base_rate in rates.items():
        exchanged = {currency: Decimal(rate / base_rate) for currency, rate in rates.items()}
        exchanged_rates[currency_key] = exchanged
    return exchanged_rates


def get_missing_rate_warning(code):
    """Return a warning string if CURRENCY_URL is configured but code has no dynamic rate."""
    if not settings.CURRENCY_URL:
        return None
    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return (
            f"No exchange rate data is available yet. "
            f"You may need to configure a static rate for {code} before users can use it."
        )
    if code not in erd.currency_exchange_dictionary:
        return (
            f"{code} has no dynamic exchange rate available. "
            f"You will need to configure a static rate before users can use it."
        )
    return None


def exchange_dictionary(rates):
    """Posts exchange rates dictionary to DB"""
    exchange_data = build_exchange_dictionary(rates)
    current_data = ExchangeRateDictionary.objects.all().first()
    if not current_data:
        ExchangeRateDictionary.objects.create(currency_exchange_dictionary=exchange_data)
    else:
        current_data.currency_exchange_dictionary = exchange_data
        current_data.save()
