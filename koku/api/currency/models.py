#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# from uuid import uuid4
# from env import currency endpoimy
from django.db import models

from api.currency.currencies import CURRENCIES
from koku.type_json_transcode import TypedJSONDecoder
from koku.type_json_transcode import TypedJSONEncoder


class ExchangeRates(models.Model):
    SUPPORTED_CURRENCIES = tuple((curr.get("code", "").lower(), curr.get("code")) for curr in CURRENCIES)

    currency_type = models.CharField(max_length=5, choices=SUPPORTED_CURRENCIES, unique=False, blank=True)
    exchange_rate = models.FloatField(default=0)


class ExchangeRateDictionary(models.Model):
    """Model provides exchange rates utilized in conversion process (Change this description)"""

    currency_exchange_dictionary = models.JSONField(null=True, encoder=TypedJSONEncoder, decoder=TypedJSONDecoder)
