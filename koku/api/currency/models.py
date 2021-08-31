#
# Copyright 2021 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Models for AWS cost entry tables."""
from uuid import uuid4

from django.db import models
from django.db.models import JSONField

class CurrencyCodes(models.Model):
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
    name = models.CharField(max_length=100, choices=SUPPORTED_CURRENCIES, unique=True)


class ExchangeRate(models.Model): 
    startingCurrency = models.ForeignKey(CurrencyCodes, related_name='column_item', on_delete=models.CASCADE)
    endingCurrency = models.ForeignKey(CurrencyCodes, related_name='row_item', on_delete=models.CASCADE)
    exchangeRate = models.FloatField()