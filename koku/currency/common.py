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
