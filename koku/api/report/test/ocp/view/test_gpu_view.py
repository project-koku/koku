#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GPU Report views."""
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
        query_params = {"group_by[vendor]": "*"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)

    def test_gpu_endpoint_with_group_by_model(self):
        """Test GPU endpoint with group_by model (GPU-specific field)."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[model]": "*"}
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
            "filter[vendor]": "nvidia",
            "group_by[node]": "*",
            "order_by[cost]": "desc",
        }
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)
        self.assertIn("meta", response.data)

    def test_gpu_endpoint_response_structure(self):
        """Test that GPU endpoint returns proper response structure with new fields."""
        url = reverse("reports-openshift-gpu")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify response structure
        self.assertIn("meta", data)
        self.assertIn("data", data)
        self.assertIn("links", data)

        # Verify meta structure
        meta = data["meta"]
        self.assertIn("count", meta)
        self.assertIn("total", meta)

    def test_gpu_endpoint_with_group_by_returns_new_fields(self):
        """Test that GPU endpoint returns memory, gpu_hours, and gpu_count fields."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[model]": "*"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # If there's data with values, verify new fields exist
        if data.get("data") and len(data["data"]) > 0:
            values = data["data"][0].get("values", [])
            if len(values) > 0:
                value = values[0]
                # Verify new fields are present
                self.assertIn("memory", value, "memory field should be present in response")
                self.assertIn("gpu_hours", value, "gpu_hours field should be present in response")
                self.assertIn("gpu_count", value, "gpu_count field should be present in response")

    def test_gpu_endpoint_order_by_memory(self):
        """Test that ordering by memory succeeds."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[model]": "*", "order_by[memory]": "desc"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gpu_endpoint_order_by_gpu_hours(self):
        """Test that ordering by gpu_hours succeeds."""
        url = reverse("reports-openshift-gpu")
        query_params = {"group_by[vendor]": "*", "order_by[gpu_hours]": "desc"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_gpu_endpoint_order_by_without_group_by(self):
        """Test that ordering by new fields works without group_by (allowlist)."""
        # These fields are in order_by_allowlist, so should work without group_by
        for field in ["memory", "gpu_hours", "gpu_count"]:
            url = reverse("reports-openshift-gpu")
            query_params = {f"order_by[{field}]": "desc"}
            url = url + "?" + urlencode(query_params, doseq=True)
            response = self.client.get(url, **self.headers)
            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK,
                f"order_by[{field}] without group_by should succeed (in allowlist)",
            )
