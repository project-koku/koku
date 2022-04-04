#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
        except (OSError, json.JSONDecodeError) as exc:
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
