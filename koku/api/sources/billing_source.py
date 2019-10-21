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

"""View for Sources-Proxy AWS and Azure billing source endpoint."""
import requests
from requests.exceptions import RequestException

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings


@never_cache
@api_view(http_method_names=['POST'])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def billing_source(request):
    """Create billing source for AWS and Azure sources."""
    request_data = request.data
    try:
        url = f'http://localhost:4000/api/cost-management/v1/billing_source/'
        response = requests.post(url, json=request_data)
        status_code = response.status_code
        response = response.json()
    except RequestException as conn_err:
        response = str(conn_err)
        status_code = status.HTTP_400_BAD_REQUEST
    return Response(response, status=status_code)
