# noqa
from django.utils.translation import ugettext as _

RH_IDENTITY_HEADER = "HTTP_X_RH_IDENTITY"

# Django will add the HTTP automatically when checking headers
CACHE_RH_IDENTITY_HEADER = "X_RH_IDENTITY"


def error_obj(key, message):
    """Create an error object."""
    error = {key: [_(message)]}
    return error


def log_json(request_id, message, context={}):
    """Create JSON object for logging data."""
    stmt = {"message": message, "request_id": request_id}
    stmt.update(context)
    return stmt
