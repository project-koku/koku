#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
from currency.common import get_currencies


LOG = logging.getLogger(__name__)


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
        data = get_currencies()
        paginator = ListPaginator(data, request)
        return paginator.paginated_response
    except (FileNotFoundError, json.JSONDecodeError):
        return Response(status=status.HTTP_404_NOT_FOUND)
