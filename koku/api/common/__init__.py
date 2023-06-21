# noqa
from uuid import UUID

from django.utils.translation import ugettext as _

RH_IDENTITY_HEADER = "HTTP_X_RH_IDENTITY"

# Django will add the HTTP automatically when checking headers
CACHE_RH_IDENTITY_HEADER = "X_RH_IDENTITY"


def error_obj(key, message):
    """Create an error object."""
    return {key: [_(message)]}


def log_json(tracing_id="", *, msg, context=None, **kwargs):
    """Create JSON object for logging data."""
    stmt = {"message": msg, "tracing_id": tracing_id}
    if context:
        stmt |= context
    stmt |= kwargs
    for key, value in stmt.items():
        if isinstance(value, UUID):
            stmt[key] = str(value)
    return stmt
