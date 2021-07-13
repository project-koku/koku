#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources listener entry point."""
import logging
import threading
import time
from http.server import HTTPServer

from django.core.management.base import BaseCommand

from koku.database import check_migrations
from koku.env import ENVIRONMENT
from sources.kafka_listener import initialize_sources_integration
from sources.management.commands.probe_server import ProbeServer


LOG = logging.getLogger(__name__)
CLOWDER_PORT = 8080
if ENVIRONMENT.bool("CLOWDER_ENABLED", default=False):
    from app_common_python import LoadedConfig

    CLOWDER_PORT = LoadedConfig.publicPort


def start_probe_server():
    """Start the probe server."""
    httpd = HTTPServer(("0.0.0.0", CLOWDER_PORT), ProbeServer)

    def start_server():
        """Start a simple webserver serving path on port"""
        httpd.RequestHandlerClass.ready = False
        httpd.serve_forever()

    LOG.info("starting liveness/readiness probe server")
    daemon = threading.Thread(name="probe_server", target=start_server)
    daemon.setDaemon(True)  # Set as a daemon so it will be killed once the main thread is dead.
    daemon.start()
    LOG.info("liveness/readiness probe server started")

    return httpd


class Command(BaseCommand):
    """Django command to launch sources kafka-listener."""

    help = "Starts koku-sources-kafka-listener"

    def handle(self, *args, **kwargs):
        httpd = start_probe_server()

        timeout = 5
        while not check_migrations():
            LOG.warning(f"Migrations not done. Sleeping {timeout} seconds.")
            time.sleep(timeout)

        httpd.RequestHandlerClass.ready = True  # Set `ready` to true to indicate migrations are done.

        LOG.info("Starting Sources Kafka Handler")
        initialize_sources_integration()
