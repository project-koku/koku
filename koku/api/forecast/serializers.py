#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Forecast Serializers."""
from rest_framework import serializers

from api.currency.currencies import CURRENCY_CHOICES
from api.report.constants import AWS_COST_TYPE_CHOICES
from api.report.serializers import handle_invalid_fields
from api.utils import get_cost_type
from api.utils import get_currency


class ForecastParamSerializer(serializers.Serializer):
    """Base Forecast Serializer."""

    limit = serializers.IntegerField(required=False, min_value=1)
    offset = serializers.IntegerField(required=False, min_value=0)
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES, required=False)

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
        if not data.get("currency"):
            data["currency"] = get_currency(self.context.get("request"))
        handle_invalid_fields(self, data)
        return data


class AWSCostForecastParamSerializer(ForecastParamSerializer):
    """AWS Cost Forecast Serializer."""

    COST_TYPE_CHOICES = AWS_COST_TYPE_CHOICES

    cost_type = serializers.ChoiceField(choices=COST_TYPE_CHOICES, required=False)

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
        return super().validate(data)


class GCPCostForecastParamSerializer(ForecastParamSerializer):
    """GCP Cost Forecast Serializer."""


class AzureCostForecastParamSerializer(ForecastParamSerializer):
    """Azure Cost Forecast Serializer."""


class OCPCostForecastParamSerializer(ForecastParamSerializer):
    """OCP Cost Forecast Serializer."""


class OCPAWSCostForecastParamSerializer(AWSCostForecastParamSerializer):
    """OCP+AWS Cost Forecast Serializer."""


class OCPAzureCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+Azure Cost Forecast Serializer."""


class OCPGCPCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+GCP Cost Forecast Serializer."""


class OCPAllCostForecastParamSerializer(ForecastParamSerializer):
    """OCP+All Cost Forecast Serializer."""
