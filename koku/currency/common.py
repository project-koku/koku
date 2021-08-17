#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common utilities and helpers for Currency."""
import json
import os

from api.iam.models import Customer
from currency.models import CurrencyOptions
from currency.models import CurrencySettings as Currency
from koku.settings import KOKU_DEFAULT_CURRENCY

CURRENCY_FILE_NAME = f"{os.path.dirname(os.path.realpath(__file__))}/specs/currencies.json"
__CURRENCY_CHOICES = None


def load_currencies_from_file():
    with open(CURRENCY_FILE_NAME) as api_file:
        data = json.load(api_file)
    return data


def load_currency_choices():
    return tuple([(currency.get("code"), currency.get("code")) for currency in load_currencies_from_file()])


def get_currencies():
    return list(CurrencyOptions.objects.values("code", "name", "symbol", "description"))


def get_choices():
    global __CURRENCY_CHOICES
    if __CURRENCY_CHOICES is None:
        __CURRENCY_CHOICES = tuple([(currency.get("code"), currency.get("code")) for currency in get_currencies()])
    return __CURRENCY_CHOICES


def get_currency_options():
    return [
        dict(
            value=currency.get("code"),
            label=f"{currency.get('code')} ({currency.get('symbol')}) - {currency.get('name')}",
        )
        for currency in get_currencies()
    ]


def get_selected_currency_or_setup(schema):
    customer = Customer.objects.filter(schema_name=schema).first()
    if not Currency.objects.filter(customer_id=customer.id).exists():
        set_currency(schema)
    currency_id = Currency.objects.filter(customer_id=customer.id).first().currency_code_id
    return CurrencyOptions.objects.filter(id=currency_id).first().code


def set_currency(schema, currency_code=KOKU_DEFAULT_CURRENCY):
    customer = Customer.objects.filter(schema_name=schema).first()
    currency = CurrencyOptions.objects.filter(code=currency_code).first()
    if currency is None:
        raise Exception("invalid currency")
    account_currency_setting = Currency.objects.filter(customer_id=customer.id)
    if not account_currency_setting.exists():
        Currency.objects.create(customer_id=customer.id, currency_code_id=currency.id)
    else:
        account_currency_setting.update(currency_code_id=currency.id)
