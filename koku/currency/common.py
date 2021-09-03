#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common utilities and helpers for Currency."""
import json
import os

from tenant_schemas.utils import schema_context

from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.currency.models import CurrencySettings

CURRENCY_FILE_NAME = f"{os.path.dirname(os.path.realpath(__file__))}/specs/currencies.json"


def load_currencies_from_file(file_path=CURRENCY_FILE_NAME):
    with open(file_path) as api_file:
        data = json.load(api_file)
        return data


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
        for currency in load_currencies_from_file()
    ]


def set_currency(schema, currency_code=KOKU_DEFAULT_CURRENCY):
    with schema_context(schema):
        account_currency_setting = CurrencySettings.objects.all().first()
        if not account_currency_setting:
            CurrencySettings.objects.create(currency=currency_code)
        else:
            account_currency_setting.currency = currency_code
            account_currency_setting.save()
