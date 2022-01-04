#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources listener entry point."""
import logging
import time

from django.core.management.base import BaseCommand

from koku.database import check_migrations
from koku.feature_flags import UNLEASH_CLIENT
from koku.probe_server import ProbeResponse
from koku.probe_server import ProbeServer
from koku.probe_server import start_probe_server
from sources.api.status import check_kafka_connection
from sources.api.status import check_sources_connection
from sources.kafka_listener import initialize_sources_integration


LOG = logging.getLogger(__name__)


class SourcesProbeServer(ProbeServer):
    """HTTP server for liveness/readiness probes."""

    def readiness_check(self):
        """Set the readiness check response."""
        status = 424
        msg = "not ready"
        if self.ready:
            if not check_kafka_connection():
                response = ProbeResponse(status, "kafka connection error")
                self._write_response(response)
                self.logger.info(response.json)
                return
            if not check_sources_connection():
                response = ProbeResponse(status, "sources-api not ready")
                self._write_response(response)
                self.logger.info(response.json)
                return
            status = 200
            msg = "ok"
        self._write_response(ProbeResponse(status, msg))


class Command(BaseCommand):
    """Django command to launch sources kafka-listener."""

    help = "Starts koku-sources-kafka-listener"

    def handle(self, *args, **kwargs):
        httpd = start_probe_server(SourcesProbeServer)

        timeout = 5
        # This is a special case because check_migrations() returns three values
        # True means migrations are up-to-date
        while check_migrations() != True:  # noqa
            LOG.warning(f"Migrations not done. Sleeping {timeout} seconds.")
            time.sleep(timeout)

        httpd.RequestHandlerClass.ready = True  # Set `ready` to true to indicate migrations are done.

        LOG.info("Initializing UNLEASH_CLIENT for sources-listener.")
        UNLEASH_CLIENT.initialize_client()

        LOG.info("Starting Sources Kafka Handler")
        initialize_sources_integration()
