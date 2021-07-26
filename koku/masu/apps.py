#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu application configuration module."""
from django.apps import AppConfig

from koku.probe_server import BasicProbeServer
from koku.probe_server import start_probe_server


class MasuConfig(AppConfig):
    """Masu application configuration."""

    name = "masu"

    def ready(self):
        """Determine if app is ready on application startup."""
        httpd = start_probe_server(BasicProbeServer)
        httpd.RequestHandlerClass.ready = True
