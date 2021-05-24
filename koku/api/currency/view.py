#
# Copyright 2021 Red Hat, Inc.
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
"""View for Currency."""
import json
import logging

from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.common.pagination import ListPaginator


CURRENCY_FILE_NAME = "koku/api/currency/specs/currencies.json"

LOG = logging.getLogger(__name__)


def load_currencies(path):
    """Obtain currency JSON data from file path."""
    with open(path) as api_file:
        data = json.load(api_file)
        return data


@api_view(("GET",))
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def get_currency(request):
    """Get Currency Data.

    This method is responsible for passing request data to the reporting APIs.

    Args:
        request (Request): The HTTP request object

    Returns:
        (Response): The report in a Response object

    """
    try:
        data = load_currencies(CURRENCY_FILE_NAME)
        paginator = ListPaginator(data, request)
        return paginator.paginated_response
    except (FileNotFoundError, json.JSONDecodeError):
        return Response(status=status.HTTP_404_NOT_FOUND)
