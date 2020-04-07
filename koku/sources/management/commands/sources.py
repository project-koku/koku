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

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections
from django.db import DEFAULT_DB_ALIAS
from django.db.migrations.executor import MigrationExecutor

from sources.kafka_listener import initialize_sources_integration

LOG = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Starts koku-sources"

    def check_migrations(self):
        connection = connections[DEFAULT_DB_ALIAS]
        connection.prepare_database()
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        return not executor.migration_plan(targets)

    def handle(self, addrport="0.0.0.0:8080", *args, **options):
        if self.check_migrations():
            LOG.info("Starting Sources Kafka Handler")
            initialize_sources_integration()

            LOG.info("Starting Sources Client Server")
            options["use_reloader"] = False
            call_command("runserver", addrport, *args, **options)
        else:
            LOG.error("Missing database migrations, Exiting...")
            exit(1)
