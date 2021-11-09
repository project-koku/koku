# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db import models


class UserSettings(models.Model):
    """A table that maps between account and settings: settings has many accounts."""

    class Meta:
        db_table = "user_settings"

    settings = models.JSONField()
