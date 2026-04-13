#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Price List views."""
import logging

from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap


class PriceListViewTests(IamTestCase):
    """Test the Price List view."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.client = APIClient()
        self.price_list_data = {
            "name": "Test Price List",
            "description": "A test price list",
            "currency": "USD",
            "effective_start_date": "2026-01-01",
            "effective_end_date": "2026-12-31",
            "rates": [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [
                        {"value": "1.50", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}
                    ],
                    "cost_type": "Infrastructure",
                }
            ],
        }

    def test_create_price_list(self):
        """Test creating a price list via the API."""
        url = reverse("price-lists-list")
        response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Test Price List")
        self.assertEqual(response.data["version"], 1)
        self.assertIsNotNone(response.data["uuid"])

    def test_create_price_list_without_name(self):
        """Test that creating a price list without a name fails."""
        url = reverse("price-lists-list")
        data = self.price_list_data.copy()
        del data["name"]
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_price_list_invalid_dates(self):
        """Test that end date before start date fails validation."""
        url = reverse("price-lists-list")
        data = self.price_list_data.copy()
        data["effective_start_date"] = "2026-12-31"
        data["effective_end_date"] = "2026-01-01"
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_price_lists(self):
        """Test listing price lists."""
        url = reverse("price-lists-list")
        # Create two price lists
        self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        data2 = self.price_list_data.copy()
        data2["name"] = "Second Price List"
        self.client.post(url, data=data2, format="json", **self.headers)

        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        # At least the 2 we created (migration may add others)
        self.assertGreaterEqual(len(results), 2)

    def test_retrieve_price_list(self):
        """Test retrieving a single price list."""
        url = reverse("price-lists-list")
        create_response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        pl_uuid = create_response.data["uuid"]

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        response = self.client.get(detail_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Price List")

    def test_update_price_list(self):
        """Test updating a price list via PUT."""
        url = reverse("price-lists-list")
        create_response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        pl_uuid = create_response.data["uuid"]

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        update_data = self.price_list_data.copy()
        update_data["name"] = "Updated Price List"
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Updated Price List")

    def test_update_rates_increments_version(self):
        """Test that updating rates via API increments version."""
        url = reverse("price-lists-list")
        create_response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        pl_uuid = create_response.data["uuid"]
        self.assertEqual(create_response.data["version"], 1)

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        update_data = self.price_list_data.copy()
        update_data["rates"] = [
            {
                "metric": {"name": "cpu_core_usage_per_hour"},
                "tiered_rates": [{"value": "3.00", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}],
                "cost_type": "Infrastructure",
            }
        ]
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], 2)

    def test_delete_price_list(self):
        """Test deleting a price list."""
        url = reverse("price-lists-list")
        create_response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        pl_uuid = create_response.data["uuid"]

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        response = self.client.delete(detail_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify it's gone
        with tenant_context(self.tenant):
            self.assertFalse(PriceList.objects.filter(uuid=pl_uuid).exists())

    def test_delete_assigned_price_list_fails(self):
        """Test that deleting a price list assigned to a cost model fails."""
        url = reverse("price-lists-list")
        create_response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        pl_uuid = create_response.data["uuid"]

        # Assign to a cost model
        with tenant_context(self.tenant):
            cost_model = CostModel.objects.first()
            PriceListCostModelMap.objects.create(
                price_list_id=pl_uuid,
                cost_model=cost_model,
                priority=1,
            )

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        response = self.client.delete(detail_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Verify it still exists
        with tenant_context(self.tenant):
            self.assertTrue(PriceList.objects.filter(uuid=pl_uuid).exists())

    def test_filter_by_name(self):
        """Test filtering price lists by name."""
        url = reverse("price-lists-list")
        self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        data2 = self.price_list_data.copy()
        data2["name"] = "Production Rates"
        self.client.post(url, data=data2, format="json", **self.headers)

        response = self.client.get(f"{url}?name=Production", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Production Rates")

    def test_retrieve_nonexistent_returns_404(self):
        """Test that retrieving a nonexistent price list returns 404."""
        detail_url = reverse("price-lists-detail", kwargs={"uuid": "00000000-0000-0000-0000-000000000099"})
        response = self.client.get(detail_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_affected_cost_models_none(self):
        """Test affected-cost-models returns empty list when not assigned."""
        url = reverse("price-lists-list")
        create_response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        pl_uuid = create_response.data["uuid"]

        affected_url = reverse("price-lists-affected-cost-models", kwargs={"uuid": pl_uuid})
        response = self.client.get(affected_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_affected_cost_models_returns_linked(self):
        """Test affected-cost-models returns cost models linked to this price list."""
        url = reverse("price-lists-list")
        create_response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        pl_uuid = create_response.data["uuid"]

        with tenant_context(self.tenant):
            cost_model = CostModel.objects.first()
            PriceListCostModelMap.objects.create(
                price_list_id=pl_uuid,
                cost_model=cost_model,
                priority=1,
            )

        affected_url = reverse("price-lists-affected-cost-models", kwargs={"uuid": pl_uuid})
        response = self.client.get(affected_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["uuid"], str(cost_model.uuid))
        self.assertEqual(response.data[0]["name"], cost_model.name)
        self.assertEqual(response.data[0]["priority"], 1)
