#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common utilities and helpers for Currency."""
import json
import os

CURRENCY_FILE_NAME = f"{os.path.dirname(os.path.realpath(__file__))}/specs/currencies.json"
__CURRENCY_DATA = None
__CURRENCY_CHOICES = None


def get_currencies():
    global __CURRENCY_DATA
    if __CURRENCY_DATA is None:
        with open(CURRENCY_FILE_NAME) as api_file:
            __CURRENCY_DATA = json.load(api_file)
    return __CURRENCY_DATA


def get_choices():
    global __CURRENCY_CHOICES
    if __CURRENCY_CHOICES is None:
        __CURRENCY_CHOICES = tuple([(currency.get("code"), currency.get("code")) for currency in get_currencies()])
    return __CURRENCY_CHOICES
