#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GPU Report views."""
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase


class OCPGpuViewTest(IamTestCase):
    """Tests for the GPU report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()

    def test_gpu_endpoint_exists(self):
        """Test that the GPU endpoint is accessible."""
        url = reverse("reports-openshift-gpu")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gpu_endpoint_with_group_by_vendor(self):
        """Test GPU endpoint with group_by vendor (GPU-specific field)."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[gpu_vendor]": "*"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)

    def test_gpu_endpoint_with_group_by_model(self):
        """Test GPU endpoint with group_by model (GPU-specific field)."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[gpu_model]": "*"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)

    def test_gpu_endpoint_order_by_uptime_should_fail(self):
        """Test that ordering by uptime fails (per Design Doc: Will Not Capture GPU usage)."""
        url = reverse("reports-openshift-gpu")
        query_params = {"order_by[uptime]": "desc"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gpu_endpoint_order_by_gpu_count_succeeds(self):
        """Test that ordering by gpu_count succeeds."""
        url = reverse("reports-openshift-gpu")
        query_params = {"order_by[gpu_count]": "desc"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gpu_endpoint_combined_params(self):
        """Test GPU endpoint with combined filter, group_by, and order_by."""
        url = reverse("reports-openshift-gpu")
        query_params = {
            "filter[gpu_vendor]": "nvidia",
            "group_by[cluster]": "*",
            "order_by[cost]": "desc",
        }
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        gpu_values = response.data["data"][0]["clusters"][0]["gpu_names"][0]["values"][0]
        self.assertGreater(len(gpu_values), 0, "GPU endpoint should return actual data")
        self.assertEqual(gpu_values["gpu_vendor"], "nvidia", "GPU vendor should be nvidia")
        self.assertIsInstance(gpu_values["gpu_memory"]["value"], Decimal, "GPU memory should be numeric")

    def test_gpu_endpoint_response_structure(self):
        """Test that GPU endpoint returns proper response structure with new fields."""
        url = reverse("reports-openshift-gpu")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gpu_endpoint_with_group_by_returns_new_fields(self):
        """Test that GPU endpoint returns memory, and gpu_count fields."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[gpu_model]": "*"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # With group_by[model], structure is: data[0]["models"][0]["values"][0]
        models = data["data"][0].get("gpu_models", [])
        self.assertGreater(len(models), 0, "Should have model groups when grouping by model")
        gpu_names = models[0].get("gpu_names", [])
        self.assertGreater(len(gpu_names), 0, "Should have gpu_names in model group")
        values = gpu_names[0].get("values", [])
        self.assertGreater(len(values), 0, "Should have values in model group")
        # Verify new fields are present
        self.assertIn("gpu_memory", values[0], "gpu_memory field should be present in response")
        self.assertIn("gpu_count", values[0], "gpu_count field should be present in response")

    def test_gpu_endpoint_order_by_memory(self):
        """Test that ordering by memory succeeds."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[gpu_model]": "*", "order_by[gpu_memory]": "desc"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gpu_endpoint_order_by_without_group_by(self):
        """Test that ordering by new fields works without group_by (allowlist)."""
        # These fields are in order_by_allowlist, so should work without group_by
        for field in ["gpu_memory", "gpu_count"]:
            url = reverse("reports-openshift-gpu")
            query_params = {f"order_by[{field}]": "desc"}
            url = url + "?" + urlencode(query_params, doseq=True)
            response = self.client.get(url, **self.headers)
            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK,
                f"order_by[{field}] without group_by should succeed (in allowlist)",
            )

    @patch("api.report.ocp.view.is_feature_flag_enabled_by_schema", return_value=False)
    def test_gpu_endpoint_blocked_when_unleash_flag_disabled(self, mock_unleash):
        """Test that GPU endpoint returns 403 when Unleash flag is disabled."""
        url = reverse("reports-openshift-gpu")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_unleash.assert_called_once()

    @patch("api.report.ocp.view.is_feature_flag_enabled_by_schema", return_value=True)
    def test_gpu_endpoint_accessible_when_unleash_flag_enabled(self, mock_unleash):
        """Test that GPU endpoint is accessible when Unleash flag is enabled."""
        url = reverse("reports-openshift-gpu")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_unleash.assert_called_once()

    def test_gpu_endpoint_with_filter_limit_and_group_by_vendor(self):
        """Test GPU endpoint with filter[limit] and group_by[vendor] does not crash."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[gpu_vendor]": "*", "filter[limit]": "1"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)

    def test_gpu_endpoint_with_filter_limit_and_group_by_model(self):
        """Test GPU endpoint with filter[limit] and group_by[model] does not crash."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[gpu_model]": "*", "filter[limit]": "1"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)

    def test_gpu_endpoint_with_filter_limit_and_group_by_cluster(self):
        """Test GPU endpoint with filter[limit] and group_by[cluster] does not crash."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[cluster]": "*", "filter[limit]": "1"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)
