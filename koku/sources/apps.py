#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources application configuration module."""
from django.apps import AppConfig


class SourcesConfig(AppConfig):
    """Sources application configuration."""

    name = "sources"

    def ready(self):
        """Register Sources post_save handlers for provider synchronization."""
        import sources.kafka_listener  # noqa: F401
