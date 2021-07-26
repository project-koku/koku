#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""API application configuration module."""
from django.apps import AppConfig

from koku.probe_server import BasicProbeServer
from koku.probe_server import start_probe_server


class ApiConfig(AppConfig):
    """API application configuration."""

    name = "api"

    def ready(self):
        """Determine if app is ready on application startup."""
        httpd = start_probe_server(BasicProbeServer)
        httpd.RequestHandlerClass.ready = True
