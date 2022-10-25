#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Forecast serializers unit tests."""
from unittest import TestCase
from unittest.mock import Mock

from rest_framework import serializers

from api.forecast.serializers import AWSCostForecastParamSerializer

# from api.forecast.serializers import AzureCostForecastParamSerializer
# from api.forecast.serializers import OCPAllCostForecastParamSerializer
# from api.forecast.serializers import OCPAWSCostForecastParamSerializer
# from api.forecast.serializers import OCPAzureCostForecastParamSerializer
# from api.forecast.serializers import OCPCostForecastParamSerializer


class ForecastParamSerializerTest(TestCase):
    """Tests the ForecastParamSerializer."""


class AWSCostForecastParamSerializerTest(TestCase):
    """Tests the AWSCostForecastParamSerializer."""

    def test_invalid_cost_type(self):
        """Test failure while handling invalid cost_type."""
        query_params = {"cost_type": "invalid_cost"}
        serializer = AWSCostForecastParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_cost_type("invalid_cost")

    def test_valid_cost_type_no_exception(self):
        """Test that a valid cost type doesn't raise an exception."""
        query_params = {"cost_type": "blended_cost"}
        req = Mock(path="/api/cost-management/v1/forecasts/aws/costs/")
        serializer = AWSCostForecastParamSerializer(data=query_params, context={"request": req})
        serializer.validate_cost_type("blended_cost")


class AzureCostForecastParamSerializerTest(TestCase):
    """Tests the AzureCostForecastParamSerializer."""


class OCPCostForecastParamSerializerTest(TestCase):
    """Tests the OCPCostForecastParamSerializer."""


class OCPAWSCostForecastParamSerializerTest(TestCase):
    """Tests the OCPAWSCostForecastParamSerializer."""


class OCPAzureCostForecastParamSerializerTest(TestCase):
    """Tests the OCPAzureCostForecastParamSerializer."""


class OCPAllCostForecastParamSerializerTest(TestCase):
    """Tests the OCAllPCostForecastParamSerializer."""
