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
import sys

from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def _collect_db_metrics():
    """Collect metrics and sleep."""
    # noqa: E402 pylint: disable=C0413
    import time
    from koku.metrics import DBSTATUS
    while True:
        DBSTATUS.collect()
        time.sleep(120)


class ApiConfig(AppConfig):
    """API application configuration."""

    name = 'api'

    def ready(self):
        """Determine if app is ready on application startup."""
        # Don't run on Django tab completion commands
        if 'manage.py' in sys.argv[0] and 'runserver' not in sys.argv:
            return
        try:
            self.db_metrics()
        except (OperationalError, ProgrammingError) as op_error:
            if 'no such table' in str(op_error) or \
                    'does not exist' in str(op_error):
                # skip this if we haven't created tables yet.
                return
            else:
                logger.error('Error: %s.', op_error)

    def db_metrics(self):  # pylint: disable=R0201
        """Create thread loop for collecting db metrics."""
        # noqa: E402 pylint: disable=C0413
        import threading
        t = threading.Thread(target=_collect_db_metrics, args=(), kwargs={})
        t.setDaemon(True)
        t.start()
