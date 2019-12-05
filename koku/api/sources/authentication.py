#
# Copyright 2019 Red Hat, Inc.
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

"""View for Sources-Proxy Azure authentications endpoint."""
import requests
from django.conf import settings
from django.utils.encoding import force_text
from requests.exceptions import RequestException
from rest_framework import status
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings


class AuthenticationException(APIException):
    """Authentication internal error exception."""

    def __init__(self, error_msg):
        """Initialize with status code 400."""
        super().__init__()
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.detail = {'detail': force_text(error_msg)}


@api_view(http_method_names=['POST'])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def authentication(request):
    """Create Subscription-ID for Azure authentication."""
    request_data = request.data
    try:
        url = f'{settings.SOURCES_CLIENT_BASE_URL}/authentication/'
        response = requests.post(url, json=request_data)
        status_code = response.status_code
        response = response.json()
        if status_code != status.HTTP_201_CREATED:
            raise AuthenticationException(str(response))
    except RequestException as conn_err:
        raise AuthenticationException(str(conn_err))
    return Response(response, status=status_code)
