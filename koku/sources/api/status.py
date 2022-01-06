#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for server status."""
import logging
import platform
import socket
import sys
from http import HTTPStatus

from django.conf import settings
from django.db import connection
from django.db import InterfaceError
from django.db import NotSupportedError
from django.db import OperationalError
from django.db import ProgrammingError
from kafka import BrokerConnection
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.config import Config
from masu.external.date_accessor import DateAccessor
from sources.config import Config as SourcesConfig
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError


LOG = logging.getLogger(__name__)

BROKER_CONNECTION = BrokerConnection(
    SourcesConfig.SOURCES_KAFKA_HOST, int(SourcesConfig.SOURCES_KAFKA_PORT), socket.AF_UNSPEC
)
BROKER_CONNECTION_ERROR = "Unable to establish connection with broker."
CELERY_WORKER_NOT_FOUND = "No running Celery workers were found."


def check_kafka_connection():
    """Check connectability of Kafka Broker."""
    connected = BROKER_CONNECTION.connect_blocking(timeout=1)
    if connected:
        BROKER_CONNECTION.close()
    return connected


def check_sources_connection():
    """Check sources-backend connection."""
    try:
        return SourcesHTTPClient(SourcesConfig.SOURCES_FAKE_HEADER).get_cost_management_application_type_id()
    except (SourcesHTTPClientError, SourceNotFoundError):
        return


@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def get_status(request):
    """Packages response for class-based view."""
    if "liveness" in request.query_params:
        return Response({"alive": True})

    if not check_kafka_connection():
        status = HTTPStatus.FAILED_DEPENDENCY
        return Response(data={"error": BROKER_CONNECTION_ERROR, "status": status}, status=status)

    if not check_sources_connection():
        status = HTTPStatus.FAILED_DEPENDENCY
        return Response(data={"error": "Sources backend not connected.", "status": status}, status=status)

    app_status = ApplicationStatus()
    response = {
        "commit": app_status.commit,
        "current_datetime": app_status.current_datetime,
        "database_status": app_status.database_status,
        "debug": app_status.debug,
        "modules": app_status.modules,
        "platform_info": app_status.platform_info,
        "python_version": app_status.python_version,
        "sources_status": app_status.sources_backend,
    }
    return Response(response)


class ApplicationStatus:
    """A view that returns status JSON."""

    def __init__(self):
        """Initialize an ApplicationStatus object."""
        self._events = {}
        self.modules = {}

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
        return DateAccessor().today()

    @property
    def debug(self):
        """Collect the debug state of the service.

        :returns: Boolean indicating debug status.
        """
        return Config.DEBUG

    @property
    def sources_backend(self):
        """Return Sources Backend connection status."""
        cost_management_type_id = check_sources_connection()
        if cost_management_type_id:
            return f"Cost Management Application ID: {cost_management_type_id}"
        else:
            return "Not connected"

    def startup(self):
        """Log startup information."""
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
