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
import logging

from django.views.decorators.vary import vary_on_headers
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from api.metrics.models import CostModelMetricsMap
from api.metrics.serializers import CostModelMetricMapSerializer

LOG = logging.getLogger(__name__)


class CostModelMetricsMapViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """CostModelMetricsMap View.

    A viewset that provides default `list()` actions.

    """

    queryset = CostModelMetricsMap.objects.all()
    serializer_class = CostModelMetricMapSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        """Get a queryset.

        Restricts the returned data to provider_uuid if supplied as a query parameter.
        """
        queryset = CostModelMetricsMap.objects.all()
        source_type = self.request.query_params.get('source_type')
        if source_type:
            queryset = queryset.filter(source_type=source_type)

        return queryset

    @vary_on_headers('User-Agent', 'Cookie')
    def list(self, request, *args, **kwargs):
        """Obtain the list of CostModelMetrics for the tenant."""
        return super().list(request=request, args=args, kwargs=kwargs)
