#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common utilities and helpers for Currency."""
from tenant_schemas.utils import schema_context

from api.currency.currencies import CURRENCIES
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.currency.models import CurrencySettings


def get_selected_currency_or_setup(schema):
    with schema_context(schema):
        if not CurrencySettings.objects.exists():
            set_currency(schema)
        currency = CurrencySettings.objects.all().first().currency
        return currency


def get_currency_options():
    return [
        dict(
            value=currency.get("code"),
            label=f"{currency.get('code')} ({currency.get('symbol')}) - {currency.get('name')}",
        )
        for currency in CURRENCIES
    ]


def set_currency(schema, currency_code=KOKU_DEFAULT_CURRENCY):
    with schema_context(schema):
        account_currency_setting = CurrencySettings.objects.all().first()
        if not account_currency_setting:
            CurrencySettings.objects.create(currency=currency_code)
        else:
            account_currency_setting.currency = currency_code
            account_currency_setting.save()
