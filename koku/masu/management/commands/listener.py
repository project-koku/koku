#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Listener entry point."""
import logging
import time

from django.core.management.base import BaseCommand

from kafka_utils.utils import check_kafka_connection
from koku.database import check_migrations
from koku.feature_flags import UNLEASH_CLIENT
from koku.probe_server import ProbeResponse
from koku.probe_server import ProbeServer
from koku.probe_server import start_probe_server
from masu.config import Config
from masu.external.kafka_msg_handler import initialize_kafka_handler


LOG = logging.getLogger(__name__)


class ListenerProbeServer(ProbeServer):
    """HTTP server for liveness/readiness probes."""

    def readiness_check(self):
        """Set the readiness check response."""
        status = 424
        msg = "not ready"
        if self.ready:
            if not check_kafka_connection(Config.INSIGHTS_KAFKA_HOST, Config.INSIGHTS_KAFKA_PORT):
                response = ProbeResponse(status, "kafka connection error")
                self._write_response(response)
                self.logger.info(response.json)
                return
            status = 200
            msg = "ok"
        self._write_response(ProbeResponse(status, msg))


class Command(BaseCommand):
    """Django command to launch listener."""

    def handle(self, *args, **kwargs):
        """Initialize the prometheus exporter and koku-listener."""
        httpd = start_probe_server(ListenerProbeServer)

        # This is a special case because check_migrations() returns three values
        # True means migrations are up-to-date
        while check_migrations() != True:  # noqa
            LOG.warning("Migrations not done. Sleeping")
            time.sleep(5)

        httpd.RequestHandlerClass.ready = True  # Set `ready` to true to indicate migrations are done.

        LOG.info("Initializing UNLEASH_CLIENT for masu-listener.")
        UNLEASH_CLIENT.initialize_client()

        LOG.info("Starting Kafka handler")
        LOG.debug("handle args: %s, kwargs: %s", str(args), str(kwargs))
        initialize_kafka_handler()
