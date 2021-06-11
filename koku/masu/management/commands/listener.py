#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Listener entry point."""
import logging
import time

from django.core.management.base import BaseCommand
from prometheus_client import start_http_server

from koku.database import check_migrations
from koku.env import ENVIRONMENT
from masu.external.kafka_msg_handler import initialize_kafka_handler
from masu.prometheus_stats import WORKER_REGISTRY


LOG = logging.getLogger(__name__)
CLOWDER_METRICS_PORT = 9999
if ENVIRONMENT.bool("CLOWDER_ENABLED", default=False):
    from app_common_python import LoadedConfig

    CLOWDER_METRICS_PORT = LoadedConfig.metricsPort


class Command(BaseCommand):
    """Django command to launch listener."""

    def handle(self, *args, **kwargs):
        """Initialize the prometheus exporter and koku-listener."""
        while not check_migrations():
            LOG.warning("Migrations not done. Sleeping")
            time.sleep(5)
        LOG.info("Initializing the prometheus exporter")
        start_http_server(CLOWDER_METRICS_PORT, registry=WORKER_REGISTRY)
        LOG.info("Starting Kafka handler")
        LOG.debug("handle args: %s, kwargs: %s", str(args), str(kwargs))
        initialize_kafka_handler()
