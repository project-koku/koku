#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Forecast Serializers."""
from rest_framework import serializers

from api.report.serializers import handle_invalid_fields


class ForecastParamSerializer(serializers.Serializer):
    """Base Forecast Serializer."""

    limit = serializers.IntegerField(required=False, min_value=1)
    offset = serializers.IntegerField(required=False, min_value=0)

    def __init__(self, *args, **kwargs):
        """Initialize the BaseSerializer."""
        self.tag_keys = kwargs.pop("tag_keys", None)
        super().__init__(*args, **kwargs)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        handle_invalid_fields(self, data)
        return data


class AWSCostForecastParamSerializer(ForecastParamSerializer):
    """AWS Cost Forecast Serializer."""


class GCPCostForecastParamSerializer(ForecastParamSerializer):
    """GCP Cost Forecast Serializer."""


class AzureCostForecastParamSerializer(ForecastParamSerializer):
    """Azure Cost Forecast Serializer."""


class OCPCostForecastParamSerializer(ForecastParamSerializer):
    """OCP Cost Forecast Serializer."""


class OCPAWSCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+AWS Cost Forecast Serializer."""


class OCPAzureCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+Azure Cost Forecast Serializer."""


class OCPGCPCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+GCP Cost Forecast Serializer."""


class OCPAllCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+All Cost Forecast Serializer."""
