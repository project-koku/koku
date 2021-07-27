#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources application configuration module."""
import logging

from django.apps import AppConfig

from koku.probe_server import BasicProbeServer
from koku.probe_server import start_probe_server


LOG = logging.getLogger(__name__)


class SourcesConfig(AppConfig):
    """Sources application configuration."""

    name = "sources"

    def ready(self):
        """Determine if app is ready on application startup."""
        httpd = start_probe_server(BasicProbeServer)
        httpd.RequestHandlerClass.ready = True
