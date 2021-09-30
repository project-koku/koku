#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for AWS cost entry tables."""
# from uuid import uuid4
from django.db import models
from django.db.models import JSONField


class ExchangeRates(models.Model):
    AUD = "aud"
    CAD = "cad"
    CHF = "chf"
    CNY = "cny"
    DKK = "dkk"
    EUR = "eur"
    GBP = "gbp"
    HKD = "hkd"
    JPY = "jpy"
    NOK = "nok"
    NZD = "nzd"
    SEK = "sek"
    SGD = "sgd"
    USD = "usd"
    ZAR = "zar"
    # SUPPORTED_CURRENCIES = tuple([(curr.code.toLower(), curr.code)for curr in CURRENCIES])
    SUPPORTED_CURRENCIES = (
        (AUD, "AUD"),
        (CAD, "CAD"),
        (CHF, "CHF"),
        (CNY, "CNY"),
        (DKK, "DKK"),
        (EUR, "EUR"),
        (GBP, "GBP"),
        (HKD, "HKD"),
        (JPY, "JPY"),
        (NOK, "NOK"),
        (NZD, "NZD"),
        (SEK, "SEK"),
        (SGD, "SGD"),
        (USD, "USD"),
        (ZAR, "ZAR"),
    )

    base_currency = models.CharField(max_length=100, choices=SUPPORTED_CURRENCIES, unique=True)
    # target_currency = models.CharField(max_length=100, choices=SUPPORTED_CURRENCIES, unique=True)
    exchangeRate = JSONField(default=dict)
