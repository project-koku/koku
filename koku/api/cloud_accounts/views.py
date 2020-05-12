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
from rest_framework.renderers import JSONRenderer
from rest_framework.settings import api_settings

from api.cloud_accounts import CLOUD_ACCOUNTS
from api.common.pagination import StandardResultsSetPagination
from api.metrics.serializers import QueryParamsSerializer


LOG = logging.getLogger(__name__)
"""View for Cloud Accounts."""


def _get_int_query_param(request, key, default):
    """Get query param integer value safely."""
    result = default
    try:
        result = int(request.query_params.get(key, default))
    except ValueError:
        pass
    return result


def get_paginator(request, count):
    """Get Paginator."""
    paginator = StandardResultsSetPagination()
    paginator.count = count
    paginator.request = request
    paginator.limit = _get_int_query_param(request, "limit", 10)
    paginator.offset = _get_int_query_param(request, "offset", 0)
    return paginator


@api_view(["GET"])
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def cloud_accounts(request):
    """View for cloud accounts."""
    serializer = QueryParamsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    paginator = get_paginator(request, len(CLOUD_ACCOUNTS))
    if paginator.limit > len(CLOUD_ACCOUNTS):
        paginator.limit = len(CLOUD_ACCOUNTS)
    try:
        data = CLOUD_ACCOUNTS[paginator.offset : paginator.offset + paginator.limit]  # noqa E203
    except IndexError:
        data = []
    return paginator.get_paginated_response(data)
