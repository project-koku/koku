#
# Copyright 2020 Red Hat, Inc.
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
import logging
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

from koku.database import check_migrations
from sources.kafka_listener import initialize_sources_integration

LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Starts koku-sources"

    def handle(self, addrport="0.0.0.0:8080", *args, **options):
        """Sources command customization point."""

        timeout = 5
        # Koku API server is responsible for running all database migrations. The sources client
        # server and kafka listener thread should only be started if migration execution is
        # complete.
        while not check_migrations():
            LOG.warning(f"Migrations not done. Sleeping {timeout} seconds.")
            time.sleep(timeout)

        LOG.info("Starting Sources Kafka Handler")
        initialize_sources_integration()

        LOG.info("Starting Sources Client Server")
        options["use_reloader"] = False
        if "skip_checks" in options:
            del options["skip_checks"]
        call_command("runserver", addrport, *args, **options)
