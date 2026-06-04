#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Currency helpers backed by the EnabledCurrency table.

All known currencies come from babel's ISO 4217 registry.  Only the
currencies that an administrator has explicitly enabled are stored in
the ``EnabledCurrency`` table (tenant schema).

Name, symbol, and description are computed at response time via babel.
"""
from babel.core import get_global
from babel.numbers import get_currency_name
from babel.numbers import get_currency_symbol
from babel.numbers import UnknownCurrencyError
from rest_framework import serializers

from api.currency.models import ExchangeRates

_ISO_4217_CURRENCIES = get_global("all_currencies")

# Backward-compatible static list (matches the 23 currencies seeded into EnabledCurrency).
# Consumers that have not migrated to the dynamic helpers can still import these.
# fmt: off
CURRENCIES = [
    {"code": "AED", "name": "United Arab Emirates Dirham", "symbol": "AED",
     "description": "AED (AED) - United Arab Emirates Dirham"},
    {"code": "AUD", "name": "Australian Dollar", "symbol": "A$",
     "description": "AUD (A$) - Australian Dollar"},
    {"code": "BRL", "name": "Brazilian Real", "symbol": "R$",
     "description": "BRL (R$) - Brazilian Real"},
    {"code": "CAD", "name": "Canadian Dollar", "symbol": "CA$",
     "description": "CAD (CA$) - Canadian Dollar"},
    {"code": "CHF", "name": "Swiss Franc", "symbol": "CHF",
     "description": "CHF (CHF) - Swiss Franc"},
    {"code": "CNY", "name": "Chinese Yuan", "symbol": "CN\u00a5",
     "description": "CNY (CN\u00a5) - Chinese Yuan"},
    {"code": "CZK", "name": "Czech Koruna", "symbol": "CZK",
     "description": "CZK (CZK) - Czech Koruna"},
    {"code": "DKK", "name": "Danish Krone", "symbol": "DKK",
     "description": "DKK (DKK) - Danish Krone"},
    {"code": "EUR", "name": "Euro", "symbol": "\u20ac",
     "description": "EUR (\u20ac) - Euro"},
    {"code": "GBP", "name": "British Pound", "symbol": "\u00a3",
     "description": "GBP (\u00a3) - British Pound"},
    {"code": "GHS", "name": "Ghanaian Cedi", "symbol": "\u20b5",
     "description": "GHS (\u20b5) - Ghanaian Cedi"},
    {"code": "HKD", "name": "Hong Kong Dollar", "symbol": "HK$",
     "description": "HKD (HK$) - Hong Kong Dollar"},
    {"code": "INR", "name": "Indian Rupee", "symbol": "\u20b9",
     "description": "INR (\u20b9) - Indian Rupee"},
    {"code": "JPY", "name": "Japanese Yen", "symbol": "\u00a5",
     "description": "JPY (\u00a5) - Japanese Yen"},
    {"code": "NGN", "name": "Nigerian Naira", "symbol": "\u20a6",
     "description": "NGN (\u20a6) - Nigerian Naira"},
    {"code": "NOK", "name": "Norwegian Krone", "symbol": "NOK",
     "description": "NOK (NOK) - Norwegian Krone"},
    {"code": "NZD", "name": "New Zealand Dollar", "symbol": "NZ$",
     "description": "NZD (NZ$) - New Zealand Dollar"},
    {"code": "SAR", "name": "Saudi Riyal", "symbol": "SAR",
     "description": "SAR (SAR) - Saudi Riyal"},
    {"code": "SEK", "name": "Swedish Krona", "symbol": "SEK",
     "description": "SEK (SEK) - Swedish Krona"},
    {"code": "SGD", "name": "Singapore Dollar", "symbol": "S$",
     "description": "SGD (S$) - Singapore Dollar"},
    {"code": "TWD", "name": "New Taiwan Dollar", "symbol": "NT$",
     "description": "TWD (NT$) - New Taiwan Dollar"},
    {"code": "USD", "name": "United States Dollar", "symbol": "$",
     "description": "USD ($) - United States Dollar"},
    {"code": "ZAR", "name": "South African Rand", "symbol": "R",
     "description": "ZAR (R) - South African Rand"},
]
# fmt: on
VALID_CURRENCIES = [currency["code"] for currency in CURRENCIES]
CURRENCY_CHOICES = tuple((currency, currency) for currency in VALID_CURRENCIES)


def get_enabled_currency_codes():
    """Return the set of currency codes that are currently enabled.

    Requires tenant schema context (set by django-tenants middleware for
    requests or by ``schema_context()`` in tasks).
    """
    from cost_models.models import EnabledCurrency

    return set(EnabledCurrency.objects.values_list("currency_code", flat=True))


class CurrencyField(serializers.CharField):
    """CharField that normalizes to uppercase and validates against enabled currencies."""

    def __init__(self, *, enabled_only, **kwargs):
        kwargs.setdefault("max_length", 5)
        self.enabled_only = enabled_only
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data).upper()
        if self.enabled_only and value not in get_enabled_currency_codes():
            raise serializers.ValidationError(f'"{value}" is not an enabled currency.')
        return value


def get_all_iso_currency_codes():
    """Return all ISO 4217 currency codes from babel's registry."""
    return _ISO_4217_CURRENCIES


def is_valid_iso_currency(code):
    """Check whether *code* is a valid ISO 4217 currency using babel's registry."""
    return code.upper() in get_all_iso_currency_codes()


def get_dynamic_rate_currencies():
    """Return the set of currency codes that have a dynamic exchange rate available."""
    return set(ExchangeRates.objects.values_list("currency_type", flat=True).distinct())


def get_currency_info(code, dynamic_rate_codes=None):
    """Return a dict with code, name, symbol, description, and dynamic rate availability.

    All metadata is resolved via babel at call time.  Falls back to the
    code itself for currencies babel does not recognise.
    """
    code = code.upper()
    try:
        name = get_currency_name(code, locale="en_US")
        symbol = get_currency_symbol(code, locale="en_US")
    except UnknownCurrencyError:
        name = code
        symbol = code

    has_dynamic_rate = dynamic_rate_codes is not None and code.lower() in dynamic_rate_codes

    return {
        "code": code,
        "name": name,
        "symbol": symbol,
        "description": f"{code} ({symbol}) - {name}",
        "has_dynamic_rate": has_dynamic_rate,
    }
