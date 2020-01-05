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

from django.shortcuts import render_to_response

from rest_framework import permissions, status
from rest_framework.decorators import (api_view,
                                       permission_classes,
                                       renderer_classes)
from rest_framework.renderers import JSONRenderer, StaticHTMLRenderer
from rest_framework.response import Response

from koku.settings import STATIC_ROOT

LOG = logging.getLogger(__name__)
OPENAPI_FILE_NAME = os.path.join(STATIC_ROOT, 'openapi.json')
OPENAPIHTML_FILE_NAME = os.path.join(STATIC_ROOT, 'openapi.html')

ext_parser = {
    'json': json.load,
    'html': lambda ioFile: ioFile.read()
}


def static_response(path):
    ext = path.split('.')[-1]
    data = None
    try:
        load = ext_parser[ext]
        with open(path) as data_file:
            try:
                data = load(data_file)
            except (IOError, json.JSONDecodeError) as exc:
                LOG.exception(exc)
    except KeyError as kexc:
        LOG.exception(kexc)
    if data:
        return Response(data)
    return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes((permissions.AllowAny,))
@renderer_classes((JSONRenderer,))
def openapi(_):
    """Provide the openapi information."""
    return static_response(OPENAPI_FILE_NAME)

@api_view(['GET'])
@permission_classes((permissions.AllowAny,))
@renderer_classes((StaticHTMLRenderer,))
def openapiHtml(_):
    """Provide the openapi information in HTML format."""
    return static_response(OPENAPIHTML_FILE_NAME)
