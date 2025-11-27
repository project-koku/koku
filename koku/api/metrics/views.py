#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Views for CostModelMetricsMap."""
import copy

from django.utils.encoding import force_str
from django.views.decorators.vary import vary_on_headers
from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.exceptions import APIException
from rest_framework.renderers import JSONRenderer
from rest_framework.settings import api_settings

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ListPaginator
from api.metrics import constants as metric_constants
from api.metrics.serializers import QueryParamsSerializer


@api_view(["GET"])  # noqa: C901
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
@vary_on_headers(CACHE_RH_IDENTITY_HEADER)
def metrics(request):
    """Provide the openapi information."""
    source_type = request.query_params.get("source_type")
    serializer = QueryParamsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    # Get account from request user for feature flag evaluation
    account = None
    try:
        account = request.user.customer.schema_name
    except AttributeError:
        pass
    cost_model_metric_map_copy = list(metric_constants.get_cost_model_metrics_map(account=account).values())
    if source_type:
        # Filter on source type
        cost_model_metric_map_copy = list(
            filter(lambda x: x.get("source_type") == source_type, cost_model_metric_map_copy)
        )
    # Convert source_type to human readable.
    for metric_map in cost_model_metric_map_copy:
        mapped_source_type = metric_map.get("source_type")
        readable_source_type = metric_constants.SOURCE_TYPE_MAP.get(mapped_source_type)
        if not (mapped_source_type and readable_source_type):
            raise CostModelMetricMapJSONException("SOURCE_TYPE_MAP or COST_MODEL_METRIC_MAP is missing a source_type.")
        metric_map["source_type"] = readable_source_type
    data = cost_model_metric_map_copy
    paginator = ListPaginator(data, request)
    return paginator.paginated_response


class CostModelMetricMapJSONException(APIException):
    """Custom internal error exception."""

    def __init__(self, message):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {"detail": force_str(message)}
