#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources application configuration module."""
import logging

from django.apps import AppConfig

LOG = logging.getLogger(__name__)


class SourcesConfig(AppConfig):
    """Sources application configuration."""

    name = "sources"

    def ready(self):
        """Determine if app is ready on application startup."""
