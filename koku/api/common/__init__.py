# noqa
from django.apps import apps as koku_apps
from django.core.exceptions import AppRegistryNotReady
from django.db import connection
from django.utils.translation import ugettext as _

RH_IDENTITY_HEADER = "HTTP_X_RH_IDENTITY"

# Django will add the HTTP automatically when checking headers
CACHE_RH_IDENTITY_HEADER = "X_RH_IDENTITY"


def error_obj(key, message):
    """Create an error object."""
    error = {key: [_(message)]}
    return error


def log_json(tracing_id, message, context={}):
    """Create JSON object for logging data."""
    stmt = {"message": message, "tracing_id": tracing_id}
    stmt.update(context)

    try:
        if (
            koku_apps.ready
            and hasattr(connection, "connection")
            and connection.connection
            and not connection.connection.closed
        ):
            stmt["db_pid"] = connection.connection.get_backend_pid()
    except AppRegistryNotReady:
        pass

    return stmt
