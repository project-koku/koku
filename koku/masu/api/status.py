#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for server status."""
import logging
import platform
import sys

from django.conf import settings
from django.db import connection
from django.db import InterfaceError
from django.db import NotSupportedError
from django.db import OperationalError
from django.db import ProgrammingError
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.utils import DateHelper
from koku import celery_app
from koku.rbac import RbacService
from masu.api import API_VERSION
from masu.config import Config
from masu.prometheus_stats import CELERY_ERRORS_COUNTER

LOG = logging.getLogger(__name__)

BROKER_CONNECTION_ERROR = "Unable to establish connection with broker."
CELERY_WORKER_NOT_FOUND = "No running Celery workers were found."


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def get_status(request):
    """Packages response for class-based view."""
    if "liveness" in request.query_params:
        return Response({"alive": True})

    app_status = ApplicationStatus()
    celery_param = request.query_params.get("celery", "false").lower()
    if celery_param == "true":
        return Response(app_status.celery_task_status)

    response = {
        "api_version": app_status.api_version,
        "celery_status": app_status.celery_status,
        "commit": app_status.commit,
        "config": {
            "debug": app_status.debug,
            "masu_retain_num_months": Config.MASU_RETAIN_NUM_MONTHS,
            "rbac_cache_ttl": RbacService().get_cache_ttl(),
        },
        "current_datetime": app_status.current_datetime,
        "database_status": app_status.database_status,
        "modules": app_status.modules,
        "platform_info": app_status.platform_info,
        "python_version": app_status.python_version,
    }
    return Response(response)


class ApplicationStatus:
    """A view that returns status JSON."""

    api_version = API_VERSION

    def __init__(self):
        """Initialize an ApplicationStatus object."""
        self._events = {}
        self.modules = {}

    @property
    def celery_status(self):
        """Determine the status of our connection to Celery.

        :returns: dict of celery status, or an error
        """
        # First check if our Broker is reachable
        conn = None
        try:
            conn = celery_app.connection()
            conn.heartbeat_check()
        except OSError:
            CELERY_ERRORS_COUNTER.inc()
            return {"Error": BROKER_CONNECTION_ERROR}
        # Now check if Celery workers are running
        stats = self._check_celery_status()
        if "Error" in stats and stats["Error"] != CELERY_WORKER_NOT_FOUND:
            stats = self._check_celery_status()
        if conn:
            conn.release()
        return stats

    @property
    def celery_task_status(self):
        """Return information on queued, reserved, and active tasks."""
        return self._get_celery_queue_data()

    def _check_celery_status(self):
        """Check for celery status."""
        try:
            conn = celery_app.connection()
            inspector = celery_app.control.inspect(connection=conn, timeout=1)
            stats = inspector.stats()
            if not stats:
                stats = {"Error": CELERY_WORKER_NOT_FOUND}
        except (ConnectionResetError, TimeoutError) as err:
            CELERY_ERRORS_COUNTER.inc()
            stats = {"Error": str(err)}
        finally:
            if conn:
                conn.release()
        return stats

    def _get_celery_queue_data(self):
        """Fetch scheduled, reserved, and running tasks."""
        tasks = {}
        try:
            conn = celery_app.connection()
            inspector = celery_app.control.inspect(connection=conn, timeout=1)

            scheduled = inspector.scheduled()
            scheduled_count = 0
            if scheduled:
                for task_list in scheduled.values():
                    scheduled_count += len(task_list)
            tasks["scheduled_count"] = scheduled_count

            reserved = inspector.reserved()
            reserved_count = 0
            if reserved:
                for task_list in reserved.values():
                    reserved_count += len(task_list)
            tasks["reserved_count"] = reserved_count
            active = inspector.active()
            active_count = 0
            if active:
                for task_list in active.values():
                    active_count += len(task_list)
            tasks["active_count"] = active_count
        except (ConnectionResetError, TimeoutError) as err:
            CELERY_ERRORS_COUNTER.inc()
            tasks = {"Error": str(err)}
        finally:
            if conn:
                conn.release()
        return tasks

    @property
    def commit(self):
        """
        Collect the build number for the server.

        :returns: A build number

        """
        return settings.GIT_COMMIT

    @property
    def database_status(self):
        """Collect database connection information.

        :returns: A dict of db connection info.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT datname AS database,
                        numbackends as database_connections
                    FROM pg_stat_database
                    """
                )
                raw = cursor.fetchall()

                # get pg_stat_database column names
                names = [desc[0] for desc in cursor.description]
        except (InterfaceError, NotSupportedError, OperationalError, ProgrammingError) as exc:
            LOG.warning("Unable to connect to DB: %s", str(exc))
            return {"ERROR": str(exc)}

        # transform list-of-lists into list-of-dicts including column names.
        result = [dict(zip(names, row)) for row in raw]

        return result

    @property
    def platform_info(self):
        """Collect the platform information.

        :returns: A dictionary of platform data
        """
        return platform.uname()._asdict()

    @property
    def python_version(self):
        """Collect the python version information.

        :returns: The python version string.
        """
        return sys.version.replace("\n", "")

    @property
    def modules(self):
        """Collect the installed modules.

        :returns: A dictonary of module names and versions.
        """
        return self._modules

    @modules.setter
    def modules(self, value):
        module_data = {
            str(name): str(module.__version__)
            for name, module in sorted(sys.modules.items())
            if hasattr(module, "__version__")
        }
        self._modules = module_data

    @property
    def current_datetime(self):
        """Collect the service current datetime.

        :returns: The datetime string.
        """
        return DateHelper().now

    @property
    def debug(self):
        """Collect the debug state of the service.

        :returns: Boolean indicating debug status.
        """
        return Config.DEBUG

    def startup(self):
        """Log startup information."""
        LOG.info("API Version: %s", self.api_version)
        LOG.info("Celery Status: %s", self.celery_status)
        LOG.info("Commit: %s", self.commit)
        LOG.info("Current Date: %s", self.current_datetime)
        LOG.info("DEBUG enabled: %s", str(self.debug))
        LOG.info("Database: %s", self.database_status)

        LOG.info("Platform:")
        for name, value in self.platform_info.items():
            LOG.info("%s - %s", name, value)

        LOG.info("Python: %s", self.python_version)
        module_list = []
        for mod, version in list(self.modules.items()):
            module_list.append(f"{mod} - {version}")

        if module_list:
            LOG.info("Modules: %s", ", ".join(module_list))
        else:
            LOG.info("Modules: None")
