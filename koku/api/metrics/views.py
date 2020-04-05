#
# Copyright 2018 Red Hat, Inc.
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
"""Views for CostModelMetricsMap."""
import copy
import logging

from django.utils.encoding import force_text
from django.views.decorators.vary import vary_on_headers
from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.exceptions import APIException
from rest_framework.renderers import JSONRenderer
from rest_framework.settings import api_settings

from api.common import RH_IDENTITY_HEADER
from api.common.pagination import StandardResultsSetPagination
from api.metrics import constants as metric_constants
from api.metrics.serializers import QueryParamsSerializer

LOG = logging.getLogger(__name__)


def get_paginator(request, count):
    """Get Paginator."""
    paginator = StandardResultsSetPagination()
    paginator.count = count
    paginator.request = request
    paginator.limit = int(request.GET.get("limit", 0))
    paginator.offset = int(request.GET.get("offset", 0))
    return paginator


@api_view(["GET"])  # noqa: C901
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
@vary_on_headers(RH_IDENTITY_HEADER)
def metrics(request):
    """Provide the openapi information."""
    source_type = request.query_params.get("source_type")
    serializer = QueryParamsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    # TODO: validate inputs in request, limit offset and source_type.
    cost_model_metric_map_copy = copy.deepcopy(metric_constants.COST_MODEL_METRIC_MAP)
    try:
        if source_type:
            # Filter on source type
            cost_model_metric_map_copy = list(
                filter(lambda x: x.get("source_type") == source_type, cost_model_metric_map_copy)
            )
        # Convert source_type to human readable.
        for metric_map in cost_model_metric_map_copy:
            metric_map["source_type"] = metric_constants.SOURCE_TYPE_MAP[metric_map["source_type"]]
    except KeyError:
        LOG.error("Malformed JSON", exc_error=True)
        raise CostModelMetricMapJSONException("Internal Error.")
    data = cost_model_metric_map_copy
    paginator = get_paginator(request, len(data))
    offset = int(request.query_params.get("offset", 0))
    limit = int(request.query_params.get("limit", 0))

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
    try:
        data = cost_model_metric_map_copy[offset : offset + limit]  # noqa E203
    except IndexError:
        data = []

    page_obj = paginator.get_paginated_response(data)

    return page_obj


class CostModelMetricMapJSONException(APIException):
    """Custom internal error exception."""

    def __init__(self, message):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {"detail": force_text(message)}
