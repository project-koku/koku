#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
