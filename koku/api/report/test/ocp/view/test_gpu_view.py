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

    def test_gpu_endpoint_order_by_gpu_count_should_fail(self):
        """Test that ordering by gpu_count fails (per Design Doc: Will Not Capture GPU usage)."""
        url = reverse("reports-openshift-gpu")
        query_params = {"order_by[gpu_count]": "desc"}
        url = url + "?" + urlencode(query_params, doseq=True)
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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
        """Test that GPU endpoint returns proper response structure with usage=0 and count=0."""
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

        # Verify usage and count are 0 (per Design Doc: Will Not Capture GPU usage)
        total = meta["total"]
        if "usage" in total:
            self.assertEqual(total["usage"]["value"], 0.0)
        if "count" in total:
            self.assertEqual(total["count"], 0.0)
