#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""API application configuration module."""
import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

from masu.processor.worker_cache import WorkerCache

LOG = logging.getLogger(__name__)


def clear_worker_cache(sender, **kwargs):
    LOG.info("Clearing worker task cache.")
    WorkerCache().invalidate_host()


class ApiConfig(AppConfig):
    """API application configuration."""

    name = "api"

    def ready(self):
        """Determine if app is ready on application startup."""
        post_migrate.connect(clear_worker_cache, sender=self)
