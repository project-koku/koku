#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Custom Koku Dev Middleware."""
from base64 import b64encode
from json import dumps as json_dumps

from api.common import RH_IDENTITY_HEADER
from django.utils.deprecation import MiddlewareMixin


class DevelopmentIdentityHeaderMiddleware(MiddlewareMixin):  # pylint: disable=too-few-public-methods
    """Middleware to add 3scale header for development."""

    header = RH_IDENTITY_HEADER

    def process_request(self, request):  # pylint: disable=no-self-use
        """Process request for to add header.

        Args:
            request (object): The request object

        """
        if hasattr(request, "META"):
            identity_header = {
                "identity": {
                    "account_number": "10001",
                    "type": "User",
                    "user": {"username": "user_dev", "email": "user_dev@foo.com", "is_org_admin": True},
                },
                "entitlements": {"openshift": {"is_entitled": True}},
            }
            json_identity = json_dumps(identity_header)
            dev_header = b64encode(json_identity.encode("utf-8"))
            request.META[self.header] = dev_header
