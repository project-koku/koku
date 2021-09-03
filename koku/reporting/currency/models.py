# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db import models


class CurrencySettings(models.Model):
    """A table that maps between account and currency: currency has many accounts."""

    class Meta:
        db_table = "currency_settings"

    currency = models.TextField()
