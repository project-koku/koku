#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""List of currencies."""
# turn off black formatting
# fmt: off
CURRENCIES = [
    {
        "code": "AED",
        "name": "United Arab Emirates Dirham",
        "symbol": "د.إ",
        "description": "AED (د.إ) - United Arab Emirates Dirham",
    },
    {
        "code": "AUD",
        "name": "Australian Dollar",
        "symbol": "A$",
        "description": "AUD (A$) - Australian Dollar",
    },
    {
        "code": "BRL",
        "name": "Brazilian Real",
        "symbol": "R$",
        "description": "BRL (R$) - Brazilian Real",
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
        "code": "CZK",
        "name": "Czech Koruna",
        "symbol": "K\u010d",
        "description": "CZK (K\u010d) - Czech Koruna",
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
        "code": "INR",
        "name": "Indian Rupee",
        "symbol": "\u20b9",
        "description": "INR (\u20b9) - Indian Rupee",
    },
    {
        "code": "JPY",
        "name": "Japanese Yen",
        "symbol": "\u00a5",
        "description": "JPY (\u00a5) - Japanese Yen",
    },
    {
        "code": "NGN",
        "name": "Nigerian Naira",
        "symbol": "\u20a6",
        "description": "NGN (\u20a6) - Nigerian Naira",
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
        "code": "SAR",
        "name": "Saudi Arabia Riyal",
        "symbol": "ر.س",
        "description": "SAR (ر.س) - Saudi Arabia Riyal",
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
        "code": "TWD",
        "name": "New Taiwan Dollar",
        "symbol": "NT$",
        "description": "TWD (NT$) - New Taiwan Dollar",
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
