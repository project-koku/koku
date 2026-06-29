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
from rest_framework import serializers

from api.currency.models import ExchangeRates
from cost_models.models import EnabledCurrency

_ISO_4217_CURRENCIES = get_global("all_currencies")


def get_enabled_currency_codes():
    """Return the set of currency codes that are currently enabled.

    Requires tenant schema context (set by django-tenants middleware for
    requests or by ``schema_context()`` in tasks).
    """
    return set(EnabledCurrency.objects.values_list("currency_code", flat=True))


class CurrencyField(serializers.CharField):
    """CharField that normalizes to uppercase and validates against enabled currencies."""

    def __init__(self, *, enabled_only, **kwargs):
        kwargs.setdefault("max_length", 5)
        self.enabled_only = enabled_only
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data).upper()
        if not is_valid_iso_currency(value):
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')
        if self.enabled_only and value not in get_enabled_currency_codes():
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')
        return value


def get_all_iso_currency_codes():
    """Return all ISO 4217 currency codes as a set from babel's registry."""
    return set(_ISO_4217_CURRENCIES)


def is_valid_iso_currency(code):
    """Check whether *code* is a valid ISO 4217 currency using babel's registry."""
    return code.upper() in get_all_iso_currency_codes()


def get_dynamic_rate_currencies():
    """Return the set of currency codes that have a dynamic exchange rate available."""
    return set(ExchangeRates.objects.values_list("currency_type", flat=True).distinct())


def get_currency_info(code, locale="en_US"):
    """Return a dict with code, name, symbol, and description.

    All metadata is resolved via babel at call time.
    Callers must validate the code before calling this function.
    """
    code = code.upper()
    name = get_currency_name(code, locale=locale)
    symbol = get_currency_symbol(code, locale=locale)

    return {
        "code": code,
        "name": name,
        "symbol": symbol,
        "description": f"{code} ({symbol}) - {name}",
    }
