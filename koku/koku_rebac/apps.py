#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django app configuration for the Kessel ReBAC integration."""
from django.apps import AppConfig


class KokuRebacConfig(AppConfig):
    """Kessel ReBAC integration app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "koku_rebac"
