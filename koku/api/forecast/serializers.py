#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Forecast Serializers."""
from rest_framework import serializers

from api.report.serializers import handle_invalid_fields
from api.utils import get_cost_type


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

    COST_TYPE_CHOICE = (
        ("blended_cost", "blended_cost"),
        ("unblended_cost", "unblended_cost"),
        ("savingsplan_effective_cost", "savingsplan_effective_cost"),
    )
    cost_type = serializers.ChoiceField(choices=COST_TYPE_CHOICE, required=False)

    def validate(self, data):
        """Validate incoming data to including cost_type.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        if not data.get("cost_type"):
            data["cost_type"] = get_cost_type(self.context.get("request"))
        handle_invalid_fields(self, data)
        return data

    def validate_cost_type(self, value):
        """Validate incoming cost_type value based on path."""

        valid_cost_type = [choice[0] for choice in self.COST_TYPE_CHOICE]
        if value not in valid_cost_type:
            error = {"cost_type": f'"{value}" is not a valid choice.'}
            raise serializers.ValidationError(error)
        return value


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


class OCPAllCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+All Cost Forecast Serializer."""
