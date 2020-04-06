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
"""CostModelMetricMap Serializer."""
from rest_framework import serializers


class CostModelMetricMapSerializer(serializers.Serializer):
    """Serializer for the CostModelMetricsMap."""

    source_type = serializers.CharField(required=True)
    metric = serializers.CharField(required=True)
    label_metric = serializers.CharField(required=True)
    label_measurement = serializers.CharField(required=True)
    label_measurement_unit = serializers.CharField(required=True)
    default_cost_type = serializers.CharField(required=True)


class QueryParamsSerializer(serializers.Serializer):
    """Validate the Query params limit and offset"""

    limit = serializers.IntegerField(required=False, min_value=1)
    offset = serializers.IntegerField(required=False, min_value=0)
