#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Forecast serializers unit tests."""
from rest_framework import serializers

from api.forecast.serializers import AWSCostForecastParamSerializer
from api.iam.test.iam_test_case import IamTestCase

# from api.forecast.serializers import AzureCostForecastParamSerializer
# from api.forecast.serializers import OCPAllCostForecastParamSerializer
# from api.forecast.serializers import OCPAWSCostForecastParamSerializer
# from api.forecast.serializers import OCPAzureCostForecastParamSerializer
# from api.forecast.serializers import OCPCostForecastParamSerializer


class ForecastParamSerializerTest(IamTestCase):
    """Tests the ForecastParamSerializer."""


class AWSCostForecastParamSerializerTest(IamTestCase):
    """Tests the AWSCostForecastParamSerializer."""

    def test_invalid_cost_type(self):
        """Test failure while handling invalid cost_type."""
        query_params = {"cost_type": "invalid_cost"}
        serializer = AWSCostForecastParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_valid_cost_type_no_exception(self):
        """Test that a valid cost type doesn't raise an exception."""
        query_params = {"cost_type": "blended_cost"}
        self.request_path = "/api/cost-management/v1/forecasts/aws/costs/"
        serializer = AWSCostForecastParamSerializer(data=query_params, context=self.ctx_w_path)
        serializer.is_valid(raise_exception=True)


class AzureCostForecastParamSerializerTest(IamTestCase):
    """Tests the AzureCostForecastParamSerializer."""


class OCPCostForecastParamSerializerTest(IamTestCase):
    """Tests the OCPCostForecastParamSerializer."""


class OCPAWSCostForecastParamSerializerTest(IamTestCase):
    """Tests the OCPAWSCostForecastParamSerializer."""


class OCPAzureCostForecastParamSerializerTest(IamTestCase):
    """Tests the OCPAzureCostForecastParamSerializer."""


class OCPAllCostForecastParamSerializerTest(IamTestCase):
    """Tests the OCAllPCostForecastParamSerializer."""
