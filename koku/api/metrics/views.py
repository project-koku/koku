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
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny

from api.common import RH_IDENTITY_HEADER
from api.metrics import constants as metric_constants
from api.metrics.serializers import CostModelMetricMapSerializer

LOG = logging.getLogger(__name__)


class CostModelMetricsMapViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """CostModelMetricsMap View.

    A viewset that provides default `list()` actions.

    """

    serializer_class = CostModelMetricMapSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """
        Return the Cost Model Metric Map data.

        Filter on source_type
        """
        source_type = self.request.query_params.get("source_type")
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

        return cost_model_metric_map_copy

    @vary_on_headers(RH_IDENTITY_HEADER)
    def list(self, request, *args, **kwargs):
        """Obtain the list of CostModelMetrics for the tenant."""
        return super().list(request=request, args=args, kwargs=kwargs)


class CostModelMetricMapJSONException(APIException):
    """Custom internal error exception."""

    def __init__(self, message):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {"detail": force_text(message)}
