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

from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from api.cloud_accounts.cloud_accounts_dictionary import CloudAccountsDictionary
from api.common.pagination import StandardResultsSetPagination
from koku.settings import STATIC_ROOT

LOG = logging.getLogger(__name__)

CLOUD_ACCOUNTS_FILE_NAME = os.path.join(STATIC_ROOT, "cloud_accounts.json")
"""View for Cloud Accounts."""


# from api.cloud_accounts.cloud_accounts_serializer


def get_paginator(request, count):
    """Determine which paginator to use based on query params."""
    # if "offset" in filter_query_params:
    #     paginator = StandardResultsSetPagination()
    #     paginator.count = count
    # else:
    paginator = StandardResultsSetPagination()
    paginator.count = count
    paginator.request = request
    paginator.limit = int(request.GET.get("limit", 0))
    paginator.offset = int(request.GET.get("offset", 0))
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
    paginator = get_paginator(request, 1)  # .GET.get("page", {})

    offset = int(request.GET.get("offset", 0))
    limit = int(request.GET.get("limit", 0))
    page = int(request.GET.get("page", 0))

    if offset > len(data) - 1:
        offset = len(data) - 1
    if offset < 0:
        offset = 0
    if limit > len(data):
        limit = len(data)
    if limit < 0:
        limit = 0
    if limit == 0:
        limit = len(data)
    if page > 0:
        offset = (page + 1) * offset
    if limit == 0:
        limit = len(data)
    if limit == 0 and offset == 0:
        data = CloudAccountsDictionary()._mapping
    else:
        data = CloudAccountsDictionary()._mapping[offset:offset + limit]

    page_obj = paginator.get_paginated_response(data)
    # TODO: add __repr__()
    if data:
        return page_obj
    return Response(status=status.HTTP_404_NOT_FOUND)
