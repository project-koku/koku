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
import json
import logging
import os

from django.utils.encoding import force_text
from django.views.decorators.vary import vary_on_headers
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny

from api.common import RH_IDENTITY_HEADER
from api.metrics.serializers import CostModelMetricMapSerializer
from koku.settings import BASE_DIR

LOG = logging.getLogger(__name__)

COST_MODEL_METRICS_FILE_NAME = os.path.join(BASE_DIR, "api/metrics/data/cost_models_metric_map.json")


class CostModelMetricsMapViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """CostModelMetricsMap View.

    A viewset that provides default `list()` actions.

    """

    serializer_class = CostModelMetricMapSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned data to provider_uuid if supplied as a query parameter.
        """
        try:
            with open(COST_MODEL_METRICS_FILE_NAME) as json_file:
                queryset = json.load(json_file)
        except (json.JSONDecodeError, OSError):
            raise CostModelMetricMapJSONException("Internal Error loading JSON")

        source_type = self.request.query_params.get("source_type")
        if source_type:
            # Query on source type
            queryset = list(filter(lambda x: x.get("source_type") == source_type, queryset))

        return queryset

    @vary_on_headers(RH_IDENTITY_HEADER)
    def list(self, request, *args, **kwargs):
        """Obtain the list of CostModelMetrics for the tenant."""
        return super().list(request=request, args=args, kwargs=kwargs)


class CostModelMetricMapJSONException(APIException):
    """Rate query custom internal error exception."""

    def __init__(self, message):
        """Initialize with status code 500."""
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.detail = {"detail": force_text(message)}
