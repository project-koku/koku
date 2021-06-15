#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Forecast view unit tests."""
from django.core.cache import caches
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions

# from api.forecast.views import AWSCostForecastView
# from api.forecast.views import AzureCostForecastView
# from api.forecast.views import OCPAllCostForecastView
# from api.forecast.views import OCPAWSCostForecastView
# from api.forecast.views import OCPAzureCostForecastView
# from api.forecast.views import OCPCostForecastView


class AWSCostForecastViewTest(IamTestCase):
    """Tests the AWSCostForecastView."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches["rbac"].clear()

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["*"]}})
    def test_get_forecast(self):
        """Test that getting a forecast works."""
        url = reverse("aws-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["*"]}})
    def test_get_forecast_invalid(self):
        """Test that getting a forecast works."""
        url = "%s?invalid=parameter" % reverse("aws-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @RbacPermissions({"aws.account": {"read": ["123", "456"]}})
    def test_get_forecast_limited_access_fail(self):
        """Test that getting a forecast with limited access returns empty result."""
        url = reverse("aws-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("meta").get("count"), 0)
        self.assertEqual(response.data.get("data"), [])

    # these account numbers are based on the contents of api/report/test/aws_static_data.yml
    @RbacPermissions(
        {"aws.account": {"read": ["9999999999991"], "aws.organizational_unit": {"read": ["9999999999991"]}}}
    )
    def test_get_forecast_limited_access_pass(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("aws-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data.get("meta").get("count"), 0)
        self.assertNotEqual(response.data.get("data"), [])


class AzureCostForecastViewTest(IamTestCase):
    """Tests the AzureCostForecastView."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches["rbac"].clear()

    @RbacPermissions({"azure.subscription_guid": {"read": ["*"]}})
    def test_get_forecast(self):
        """Test that gettng a forecast works."""
        url = reverse("azure-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class OCPCostForecastViewTest(IamTestCase):
    """Tests the OCPCostForecastView."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches["rbac"].clear()

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.node": {"read": ["*"]}})
    def test_get_forecast(self):
        """Test that gettng a forecast works."""
        url = reverse("openshift-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class OCPAWSCostForecastViewTest(IamTestCase):
    """Tests the OCPAWSCostForecastView."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches["rbac"].clear()

    @RbacPermissions(
        {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": ["*"]},
            "openshift.cluster": {"read": ["*"]},
            "openshift.node": {"read": ["*"]},
        }
    )
    def test_get_forecast(self):
        """Test that gettng a forecast works."""
        url = reverse("openshift-aws-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class OCPAzureCostForecastViewTest(IamTestCase):
    """Tests the OCPAzureCostForecastView."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches["rbac"].clear()

    @RbacPermissions(
        {
            "azure.subscription_guid": {"read": ["*"]},
            "openshift.cluster": {"read": ["*"]},
            "openshift.node": {"read": ["*"]},
        }
    )
    def test_get_forecast(self):
        """Test that gettng a forecast works."""
        url = reverse("openshift-azure-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class OCPAllCostForecastViewTest(IamTestCase):
    """Tests the OCAllPCostForecastView."""

    def setUp(self):
        """Set up the rate view tests."""
        super().setUp()
        caches["rbac"].clear()

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.node": {"read": ["*"]}})
    def test_get_forecast(self):
        """Test that gettng a forecast works."""
        url = reverse("openshift-all-cost-forecasts")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
