#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu application configuration module."""
from django.apps import AppConfig


class MasuConfig(AppConfig):
    """Masu application configuration."""

    name = "masu"

    def ready(self):
        """Determine if app is ready on application startup."""
