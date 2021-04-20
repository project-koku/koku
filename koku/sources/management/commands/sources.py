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

from django.core.management.base import BaseCommand
from gunicorn.app.base import BaseApplication

from koku.database import check_migrations
from koku.env import ENVIRONMENT
from koku.wsgi import application
from sources.kafka_listener import initialize_sources_integration

LOG = logging.getLogger(__name__)


class SourcesApplication(BaseApplication):
    # reference https://docs.gunicorn.org/en/latest/custom.html
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {key: value for key, value in self.options.items() if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


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
        if ENVIRONMENT.bool("RUN_GUNICORN", default=True):
            options = {"bind": "{}:{}".format("0.0.0.0", "8080"), "workers": 1, "timeout": 90, "loglevel": "info"}
            SourcesApplication(application, options).run()
        else:
            from django.core.management import call_command

            options["use_reloader"] = False
            options.pop("skip_checks", None)
            call_command("runserver", addrport, *args, **options)
