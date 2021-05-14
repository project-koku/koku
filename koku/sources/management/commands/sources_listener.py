#
# Copyright 2021 Red Hat, Inc.
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
