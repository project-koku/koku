#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from decimal import Decimal

from django.conf import settings

from api.currency.models import ExchangeRateDictionary
from cost_models.models import MonthlyExchangeRate


def build_exchange_dictionary(rates):
    """Build the exchange rates dictionary"""
    exchanged_rates = {}
    for currency_key, base_rate in rates.items():
        exchanged = {currency: Decimal(rate / base_rate) for currency, rate in rates.items()}
        exchanged_rates[currency_key] = exchanged
    return exchanged_rates


def get_missing_rate_warning(code):
    """Return a warning string if the currency has no exchange rates configured."""
    has_rate = MonthlyExchangeRate.objects.filter(target_currency=code).exists()
    if has_rate:
        return None
    if settings.CURRENCY_URL:
        return (
            f"No exchange rate available for {code}. "
            f"You may need to configure a static rate before users can use it."
        )
    return (
        f"No exchange rate available for {code}. "
        f"Configure a static rate or enable dynamic exchange rates before users can use it."
    )


def exchange_dictionary(rates):
    """Posts exchange rates dictionary to DB"""
    exchange_data = build_exchange_dictionary(rates)
    current_data = ExchangeRateDictionary.objects.all().first()
    if not current_data:
        ExchangeRateDictionary.objects.create(currency_exchange_dictionary=exchange_data)
    else:
        current_data.currency_exchange_dictionary = exchange_data
        current_data.save()
