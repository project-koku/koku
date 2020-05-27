#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Listener entry point."""
import logging
import time

from django.core.management.base import BaseCommand
from prometheus_client import start_http_server

from koku.database import check_migrations
from masu.external.kafka_msg_handler import initialize_kafka_handler
from masu.prometheus_stats import WORKER_REGISTRY


LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django command to launch listener."""

    def handle(self, *args, **kwargs):
        """Initialize the prometheus exporter and koku-listener."""
        while not check_migrations():
            LOG.warning("Migrations not done. Sleeping")
            time.sleep(5)
        LOG.info("Initializing the prometheus exporter")
        start_http_server(9999, registry=WORKER_REGISTRY)
        LOG.info("Starting Kafka handler")
        LOG.debug("handle args: %s, kwargs: %s", str(args), str(kwargs))
        initialize_kafka_handler()
