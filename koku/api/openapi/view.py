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
"""View for openapi documentation."""
import json
import logging
import os

from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from koku.settings import STATIC_ROOT

LOG = logging.getLogger(__name__)
OPENAPI_FILE_NAME = os.path.join(STATIC_ROOT, "openapi.json")


def get_json(path):
    """Obtain API JSON data from file path."""
    json_data = None
    with open(path) as json_file:
        try:
            json_data = json.load(json_file)
        except (IOError, json.JSONDecodeError) as exc:
            LOG.exception(exc)
    return json_data


@api_view(["GET"])
@permission_classes((permissions.AllowAny,))
@renderer_classes((JSONRenderer,))
def openapi(_):
    """Provide the openapi information."""
    data = get_json(OPENAPI_FILE_NAME)
    if data:
        return Response(data)
    return Response(status=status.HTTP_404_NOT_FOUND)
