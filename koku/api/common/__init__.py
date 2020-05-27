# noqa
from django.utils.translation import ugettext as _

RH_IDENTITY_HEADER = "HTTP_X_RH_IDENTITY"


def error_obj(key, message):
    """Create an error object."""
    error = {key: [_(message)]}
    return error
