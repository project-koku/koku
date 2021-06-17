#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources listener entry point."""
import logging
import time

from django.core.management.base import BaseCommand

from koku.database import check_migrations
from sources.kafka_listener import initialize_sources_integration


LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django command to launch sources kafka-listener."""

    help = "Starts koku-sources-kafka-listener"

    def handle(self, *args, **kwargs):
        timeout = 5
        while not check_migrations():
            LOG.warning(f"Migrations not done. Sleeping {timeout} seconds.")
            time.sleep(timeout)

        LOG.info("Starting Sources Kafka Handler")
        initialize_sources_integration()
