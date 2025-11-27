#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Metrics views."""
from unittest.mock import patch
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.metrics.constants import get_cost_model_metrics_map
from api.metrics.constants import SOURCE_TYPE_MAP
from api.models import Provider


class CostModelMetricsMapViewTest(IamTestCase):
    """Tests for the metrics view."""

    def test_list_cost_model_metrics_maps(self):
        """Test that a list GET call works for the Metrics Map."""
        url = reverse("metrics")
        client = APIClient()

        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data.get("data", [])
        db_source_types = list(SOURCE_TYPE_MAP.keys())
        ui_source_types = list(SOURCE_TYPE_MAP.values())
        for entry in data:
            self.assertNotIn(entry.get("source_type"), db_source_types)
            self.assertIn(entry.get("source_type"), ui_source_types)

    def test_list_cost_model_metrics_maps_source_filter(self):
        """Test that a list GET call works with a source_type filter."""
        url = reverse("metrics")
        client = APIClient()

        params = {"source_type": Provider.PROVIDER_OCP}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_cost_model_metrics_maps_source_filter(self):
        """Test that a POST call does not work for the Metrics Map."""
        url = reverse("metrics")
        client = APIClient()

        params = {"source_type": Provider.PROVIDER_OCP}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.post(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_cost_model_metrics_maps_source_filter(self):
        """Test that DELETE call does not work for the Metrics Map."""
        url = reverse("metrics")
        client = APIClient()

        params = {"source_type": Provider.PROVIDER_OCP}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.delete(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_metric_map_values(self):
        """
        Test contents of the metrics.

        Test that the COST_MODEL_METRIC_MAP constant is properly formatted and contains the required data.
        """
        url = reverse("metrics")
        client = APIClient()

        metric_map = get_cost_model_metrics_map()

        params = {"source_type": Provider.PROVIDER_OCP}
        url = url + "?" + urlencode(params, quote_via=quote_plus) + f"&limit={len(metric_map)}"
        response = client.get(url, **self.headers).data["data"]
        self.assertEqual(len(metric_map), len(response))
        for metric in metric_map.values():
            self.assertIsNotNone(metric.get("source_type"))
            self.assertIsNotNone(metric.get("metric"))
            self.assertIsNotNone(metric.get("label_metric"))
            self.assertIsNotNone(metric.get("label_measurement_unit"))
            self.assertIsNotNone(metric.get("default_cost_type"))

    def test_emptry_return_valid_source_type(self):
        """
        Test contents of the metrics.

        Test that the data is empty list when not OCP source_type is supplied.
        """
        url = reverse("metrics")
        client = APIClient()

        url = url + f"?source_type={Provider.PROVIDER_AWS}"
        response_data = client.get(url, **self.headers).data["data"]
        self.assertFalse(response_data)

    def test_limit_1_offset_1(self):
        """
        Test accessing the second element in the array.
        """
        url = reverse("metrics")
        client = APIClient()
        data = client.get(url + "?limit=1&offset=1", **self.headers).data["data"]
        self.assertEqual(1, len(data))

    def test_invalid_query_params(self):
        """
        Test invalid query parameters, for example ?limit=foo
        """
        url = reverse("metrics")
        client = APIClient()

        params = {"limit": "foo"}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_response(self):
        """Test accessing an empty page."""
        url = reverse("metrics")
        offset = len(get_cost_model_metrics_map())
        client = APIClient()
        data = client.get(url + "?limit=1&offset=" + str(offset), **self.headers).data["data"]
        self.assertEqual([], data)

    def test_invalid_json_500_response(self):
        """Test that the API returns a 500 error when there is invalid cost model metric map."""
        url = reverse("metrics")
        client = APIClient()
        MOCK_COST_MODEL_METRIC_MAP = {"Invalid": {"Invalid": "Invalid"}}
        with patch("api.metrics.constants.get_cost_model_metrics_map", return_value=MOCK_COST_MODEL_METRIC_MAP):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_invalid_json_500_response_source_type_map(self):
        """Test that the API returns a 500 error when there is invalid source type map."""
        url = reverse("metrics")
        client = APIClient()
        MOCK_SOURCE_TYPE_MAP = {"OCP-is-missing-from-this-dict": "Invalid"}
        with patch("api.metrics.constants.SOURCE_TYPE_MAP", MOCK_SOURCE_TYPE_MAP):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_catch_value_error(self):
        """Test that the API handles an invalid limit."""
        url = reverse("metrics")
        offset = len(get_cost_model_metrics_map())
        client = APIClient()
        data = client.get(url + "?limit=&offset=" + str(offset), **self.headers).data["data"]
        self.assertEqual([], data)

    def test_gpu_cost_metric_structure(self):
        """Test that GPU cost model metric has correct structure."""
        # Verify constant exists
        self.assertEqual(metric_constants.OCP_GPU_MONTH, "gpu_cost_per_month")

        # Verify it's in the choices
        self.assertIn(metric_constants.OCP_GPU_MONTH, metric_constants.METRIC_CHOICES)

        # Verify it's NOT in monthly rates
        self.assertNotIn(metric_constants.OCP_GPU_MONTH, metric_constants.COST_MODEL_MONTHLY_RATES)

        # Verify it's in the UNLEASH_METRICS_GPU
        self.assertIn("gpu_cost_per_month", metric_constants.UNLEASH_METRICS_GPU)
        gpu_metric = metric_constants.UNLEASH_METRICS_GPU["gpu_cost_per_month"]
        self.assertEqual(gpu_metric["label_metric"], "GPU")
        self.assertEqual(gpu_metric["label_measurement_unit"], "gpu-month")
        self.assertEqual(gpu_metric["default_cost_type"], "Infrastructure")
        self.assertEqual(gpu_metric["source_type"], "OCP")

    @patch("api.metrics.constants.is_feature_flag_enabled_by_account", return_value=False)
    def test_gpu_metric_hidden_when_flag_disabled(self, mock_unleash):
        """Test GPU metric is not available when Unleash flag is disabled."""
        metrics = get_cost_model_metrics_map(account=self.schema_name)
        self.assertNotIn("gpu_cost_per_month", metrics)

    @patch("api.metrics.constants.is_feature_flag_enabled_by_account", return_value=True)
    def test_gpu_metric_visible_when_flag_enabled(self, mock_unleash):
        """Test GPU metric is available when Unleash flag is enabled."""
        metrics = get_cost_model_metrics_map(account=self.schema_name)
        self.assertIn("gpu_cost_per_month", metrics)
        gpu_metric = metrics["gpu_cost_per_month"]
        self.assertEqual(gpu_metric["label_metric"], "GPU")

    @patch("api.metrics.constants.is_feature_flag_enabled_by_account")
    def test_metrics_endpoint_extracts_account_from_user(self, mock_unleash):
        """Test that /metrics/ endpoint extracts account from request.user"""
        mock_unleash.return_value = True
        url = reverse("metrics")
        client = APIClient()

        # Call endpoint with authenticated user (from IamTestCase)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify unleash was called
        self.assertTrue(mock_unleash.called)

    @patch("api.metrics.constants.is_feature_flag_enabled_by_account")
    def test_metrics_endpoint_with_user_missing_customer(self, mock_unleash):
        """Test /metrics/ when request.user doesn't have customer attribute."""
        mock_unleash.return_value = False
        url = reverse("metrics")
        client = APIClient()

        # Patch hasattr to simulate user without customer
        with patch("api.metrics.views.hasattr") as mock_hasattr:
            mock_hasattr.side_effect = [True, False]
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            # Unleash should be called with account=None
            mock_unleash.assert_called()
