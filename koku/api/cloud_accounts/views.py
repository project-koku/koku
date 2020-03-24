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
"""View for Cloud Account."""
import json
import logging
import os

from django.core.paginator import Paginator
from django.shortcuts import render
from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from api.common.pagination import StandardResultsSetPagination
from api.query_params import QueryParameters
from rest_framework.serializers import ValidationError

from koku.settings import STATIC_ROOT

LOG = logging.getLogger(__name__)

CLOUD_ACCOUNTS_FILE_NAME = os.path.join(STATIC_ROOT, "cloud_accounts.json")
"""View for Cloud Accounts."""

from api.common.pagination import ReportPagination
from api.common.pagination import ReportRankedPagination
from api.cloud_accounts.cloud_accounts_dictionary import CloudAccountsDictionary
from api.cloud_accounts.cloud_accounts_serializer

def get_paginator(filter_query_params, count):
    """Determine which paginator to use based on query params."""
    if "offset" in filter_query_params:
        paginator = ReportRankedPagination()
        paginator.count = count
    else:
        paginator = ReportPagination()
    return paginator


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
@renderer_classes([BrowsableAPIRenderer, JSONRenderer])
def cloudaccounts(request):
    """Provide the openapi information."""
    data = CloudAccountsDictionary()._mapping
    paginator = Paginator(data, 1)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    # paginator = get_paginator(params.parameters.get("filter", {}), max_rank)
    # paginated_result = paginator.paginate_queryset(output, request)
    # LOG.debug(f"DATA: {output}")
    # if data:
    # return paginator.get_paginated_response(paginated_result)
    if data:
        return Response(list(page_obj))
    return Response(status=status.HTTP_404_NOT_FOUND)
