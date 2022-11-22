#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""List of currencies."""
# turn off black formatting
# fmt: off
CURRENCIES = [
    {
        "code": "AUD",
        "name": "Australian Dollar",
        "symbol": "A$",
        "description": "AUD (A$) - Australian Dollar",
    },
    {
        "code": "CAD",
        "name": "Canadian Dollar",
        "symbol": "CA$",
        "description": "CAD (CA$) - Canadian Dollar",
    },
    {
        "code": "CHF",
        "name": "Swiss Franc",
        "symbol": "CHF",
        "description": "CHF (CHF) - Swiss Franc",
    },
    {
        "code": "CNY",
        "name": "Chinese Yuan",
        "symbol": "CN\u00a5",
        "description": "CNY (CN\u00a5) - Chinese Yuan",
    },
    {
        "code": "DKK",
        "name": "Danish Krone",
        "symbol": "DKK",
        "description": "DKK (DKK) - Danish Krone",
    },
    {
        "code": "EUR",
        "name": "Euro",
        "symbol": "\u20ac",
        "description": "EUR (\u20ac) - Euro",
    },
    {
        "code": "GBP",
        "name": "British Pound",
        "symbol": "\u00a3",
        "description": "GBP (\u00a3) - British Pound",
    },
    {
        "code": "HKD",
        "name": "Hong Kong Dollar",
        "symbol": "HK$",
        "description": "HKD (HK$) - Hong Kong Dollar",
    },
    {
        "code": "JPY",
        "name": "Japanese Yen",
        "symbol": "\u00a5",
        "description": "JPY (\u00a5) - Japanese Yen",
    },
    {
        "code": "NOK",
        "name": "Norwegian Krone",
        "symbol": "NOK",
        "description": "NOK (NOK) - Norwegian Krone",
    },
    {
        "code": "NZD",
        "name": "New Zealand Dollar",
        "symbol": "NZ$",
        "description": "NZD (NZ$) - New Zealand Dollar",
    },
    {
        "code": "SEK",
        "name": "Swedish Krona",
        "symbol": "SEK",
        "description": "SEK (SEK) - Swedish Krona",
    },
    {
        "code": "SGD",
        "name": "Singapore Dollar",
        "symbol": "SGD",
        "description": "SGD (SGD) - Singapore Dollar",
    },
    {
        "code": "USD",
        "name": "United States Dollar",
        "symbol": "$",
        "description": "USD ($) - United States Dollar",
    },
    {
        "code": "ZAR",
        "name": "South African Rand",
        "symbol": "ZAR",
        "description": "ZAR (ZAR) - South African Rand",
    },
]
# fmt: on
VALID_CURRENCIES = [currency["code"] for currency in CURRENCIES]
CURRENCY_CHOICES = tuple((currency, currency) for currency in VALID_CURRENCIES)
