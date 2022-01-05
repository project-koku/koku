#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import importlib
import logging
import time

from django.core.management.base import BaseCommand
from gunicorn.app.base import BaseApplication

from koku.database import check_migrations
from koku.env import ENVIRONMENT
from koku.wsgi import application
from sources.kafka_listener import initialize_sources_integration

LOG = logging.getLogger(__name__)
CLOWDER_PORT = 8080
if ENVIRONMENT.bool("CLOWDER_ENABLED", default=False):
    from app_common_python import LoadedConfig

    CLOWDER_PORT = LoadedConfig.publicPort


def get_config_from_module_name(module_name):
    return vars(importlib.import_module(module_name))


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

    def handle(self, addrport=f"0.0.0.0:{CLOWDER_PORT}", *args, **options):
        """Sources command customization point."""

        timeout = 5
        # Koku API server is responsible for running all database migrations. The sources client
        # server and kafka listener thread should only be started if migration execution is
        # complete.
        # This is a special case because check_migrations() returns three values
        # True means migrations are up-to-date
        while check_migrations() != True:  # noqa
            LOG.warning(f"Migrations not done. Sleeping {timeout} seconds.")
            time.sleep(timeout)

        LOG.info("Starting Sources Kafka Handler")
        initialize_sources_integration()

        LOG.info("Starting Sources Client Server")
        if ENVIRONMENT.bool("RUN_GUNICORN", default=True):
            options = get_config_from_module_name("gunicorn_conf")
            options["bind"] = addrport
            SourcesApplication(application, options).run()
        else:
            from django.core.management import call_command

            options["use_reloader"] = False
            options.pop("skip_checks", None)
            call_command("runserver", addrport, *args, **options)
