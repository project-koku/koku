# noqa
import binascii
import logging
from base64 import b64decode
from json import loads as json_loads
from json.decoder import JSONDecodeError

LOG = logging.getLogger(__name__)
HEADER_X_RH_IDENTITY = "X-Rh-Identity"


def get_auth_header(request):
    """Get the auth header from the request."""
    return request.headers.get(HEADER_X_RH_IDENTITY)


def get_param_from_header(request, search_param):
    """Get param from header."""
    param = None
    auth_header = get_auth_header(request)
    if auth_header:
        try:
            decoded_rh_auth = b64decode(auth_header)
            json_rh_auth = json_loads(decoded_rh_auth)
            param = json_rh_auth.get("identity", {}).get(search_param)
        except (binascii.Error, JSONDecodeError) as error:
            LOG.error(f"Error decoding authentication header: {str(error)}")
    return param
