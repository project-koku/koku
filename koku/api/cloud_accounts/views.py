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
import logging

from rest_framework import permissions
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.renderers import JSONRenderer

from api.cloud_accounts.cloud_accounts_dictionary import CLOUD_ACCOUNTS_DICTIONARY
from api.common.pagination import StandardResultsSetPagination

LOG = logging.getLogger(__name__)

"""View for Cloud Accounts."""


def get_paginator(request, count):
    """Get Paginator."""
    paginator = StandardResultsSetPagination()
    paginator.count = count
    paginator.request = request
    paginator.limit = int(request.GET.get("limit", 0))
    paginator.offset = int(request.GET.get("offset", 0))
    return paginator


@api_view(["GET"])
@permission_classes((permissions.AllowAny,))
@renderer_classes([BrowsableAPIRenderer, JSONRenderer])
def cloudaccounts(request):
    """Provide the openapi information."""
    data = CLOUD_ACCOUNTS_DICTIONARY
    paginator = get_paginator(request, len(data))
    offset = int(request.query_params.get("offset", 0))
    limit = int(request.query_params.get("limit", 0))
    page = int(request.query_params.get("page", 0))

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
        if offset > 0:
            offset = (page + 1) * offset
        else:
            offset = page * 1
    try:
        data = CLOUD_ACCOUNTS_DICTIONARY[offset : offset + limit]  # noqa E203
    except IndexError:
        data = []
    page_obj = paginator.get_paginated_response(data)

    return page_obj
