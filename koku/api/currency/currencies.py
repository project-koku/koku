#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Currency helpers backed by the EnabledCurrency table.

No hardcoded currency list.  Currencies are discovered dynamically by the
daily Celery task and managed via the EnabledCurrency table (tenant schema).
Administrators enable currencies through the Settings UI.

Display metadata (name, symbol) is resolved via babel at discovery time
and stored on the EnabledCurrency row.
"""
from babel.numbers import get_currency_name
from babel.numbers import get_currency_symbol
from babel.numbers import UnknownCurrencyError

from cost_models.models import EnabledCurrency


def get_enabled_currency_codes():
    """Return the set of currency codes that are currently enabled.

    Requires tenant schema context (set by django-tenants middleware for
    requests or by ``schema_context()`` in tasks).
    """
    return set(EnabledCurrency.objects.filter(enabled=True).values_list("currency_code", flat=True))


def get_all_currency_codes():
    """Return the set of all known currency codes (enabled or not).

    Requires tenant schema context.
    """
    return set(EnabledCurrency.objects.values_list("currency_code", flat=True))


def lookup_currency_metadata(code):
    """Resolve a currency code to its display name and symbol via babel.

    Returns (name, symbol) tuple.  Falls back to the code itself for
    currencies babel does not recognise (e.g. crypto or non-standard
    codes returned by some exchange rate APIs).
    """
    code = code.upper()
    try:
        name = get_currency_name(code, locale="en_US")
        symbol = get_currency_symbol(code, locale="en_US")
    except UnknownCurrencyError:
        name = code
        symbol = code
    return name, symbol
