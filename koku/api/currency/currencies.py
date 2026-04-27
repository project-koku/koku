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

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 5)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data).upper()
        if value not in get_enabled_currency_codes():
            raise serializers.ValidationError(f'"{value}" is not an enabled currency.')
        return value


def is_valid_iso_currency(code):
    """Check whether *code* is a valid ISO 4217 currency using babel's registry."""
    return code.upper() in _ISO_4217_CURRENCIES


def get_currency_info(code):
    """Return a dict with code, name, symbol, and description for a currency.

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
    return {
        "code": code,
        "name": name,
        "symbol": symbol,
        "description": f"{code} ({symbol}) - {name}",
    }
