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

    def _create_price_list(self, **overrides):
        """Helper to create a price list via the API."""
        url = reverse("price-lists-list")
        data = {**self.price_list_data, **overrides}
        # Keep rate unit in sync with the price list currency
        if "currency" in overrides and "rates" not in overrides:
            data["rates"] = [
                {
                    **rate,
                    "tiered_rates": [{**tr, "unit": overrides["currency"]} for tr in rate.get("tiered_rates", [])],
                }
                for rate in data["rates"]
            ]
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response

    # --- Create ---

    def test_create_price_list(self):
        """Test creating a price list via the API."""
        response = self._create_price_list()
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

    def test_create_price_list_start_date_not_first_of_month(self):
        """Test that start date not on first of month fails validation."""
        url = reverse("price-lists-list")
        data = self.price_list_data.copy()
        data["effective_start_date"] = "2026-01-15"
        data["effective_end_date"] = "2026-12-31"
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("effective_start_date must be on the first day of the month", str(response.data))

    def test_create_price_list_end_date_not_last_of_month(self):
        """Test that end date not on last of month fails validation."""
        url = reverse("price-lists-list")
        data = self.price_list_data.copy()
        data["effective_start_date"] = "2026-01-01"
        data["effective_end_date"] = "2026-12-15"
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("effective_end_date must be on the last day of the month", str(response.data))

    # --- List ---

    def test_list_price_lists(self):
        """Test listing price lists."""
        self._create_price_list(name="First Price List")
        self._create_price_list(name="Second Price List")

        url = reverse("price-lists-list")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        self.assertGreaterEqual(len(results), 2)

    # --- Retrieve ---

    def test_retrieve_price_list(self):
        """Test retrieving a single price list."""
        create_response = self._create_price_list()
        pl_uuid = create_response.data["uuid"]

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        response = self.client.get(detail_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Price List")

    def test_retrieve_nonexistent_returns_404(self):
        """Test that retrieving a nonexistent price list returns 404."""
        detail_url = reverse("price-lists-detail", kwargs={"uuid": "00000000-0000-0000-0000-000000000099"})
        response = self.client.get(detail_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Update ---

    def test_update_price_list(self):
        """Test updating a price list via PUT."""
        create_response = self._create_price_list()
        pl_uuid = create_response.data["uuid"]

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        update_data = self.price_list_data.copy()
        update_data["name"] = "Updated Price List"
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Updated Price List")

    def test_update_rates_increments_version(self):
        """Test that updating rates via API increments version."""
        create_response = self._create_price_list()
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

    def test_update_currency_fails(self):
        """Test that updating currency fails - currency is immutable."""
        create_response = self._create_price_list(currency="USD")
        pl_uuid = create_response.data["uuid"]
        self.assertEqual(create_response.data["currency"], "USD")

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        update_data = self.price_list_data.copy()
        update_data["currency"] = "EUR"
        update_data["rates"] = [
            {
                "metric": {"name": "cpu_core_usage_per_hour"},
                "tiered_rates": [{"value": "1.50", "unit": "EUR", "usage": {"usage_start": None, "usage_end": None}}],
                "cost_type": "Infrastructure",
            }
        ]
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Currency cannot be changed", str(response.data))

    def test_update_without_currency_successful(self):
        """Test that updating without specifying currency preserves the existing currency."""
        create_response = self._create_price_list(currency="USD")
        pl_uuid = create_response.data["uuid"]
        self.assertEqual(create_response.data["currency"], "USD")

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        update_data = self.price_list_data.copy()
        update_data["name"] = "Updated Name"
        # omit currency from update_data
        del update_data["currency"]
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currency"], "USD")

    # --- Delete ---

    def test_delete_price_list(self):
        """Test deleting a price list."""
        create_response = self._create_price_list()
        pl_uuid = create_response.data["uuid"]

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        response = self.client.delete(detail_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        with tenant_context(self.tenant):
            self.assertFalse(PriceList.objects.filter(uuid=pl_uuid).exists())

    def test_delete_assigned_price_list_fails(self):
        """Test that deleting a price list assigned to a cost model fails."""
        create_response = self._create_price_list()
        pl_uuid = create_response.data["uuid"]

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

        with tenant_context(self.tenant):
            self.assertTrue(PriceList.objects.filter(uuid=pl_uuid).exists())

    # --- Filtering (bracket notation) ---

    def test_filter_by_name_single_value(self):
        """Test filtering price lists by name with a single value."""
        self._create_price_list(name="Production Rates")
        self._create_price_list(name="Staging Rates")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?filter[name]=Production", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Production Rates")

    def test_filter_by_name_csv_one_match(self):
        """Test OR filtering with comma-separated values where only one matches."""
        self._create_price_list(name="Production Rates")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?filter[name]=Production,Nonexistent", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        matching = [r for r in results if r["name"] == "Production Rates"]
        self.assertEqual(len(matching), 1)

    def test_filter_by_name_repeated_params_both_match(self):
        """Test OR filtering with repeated bracket params where both values match."""
        self._create_price_list(name="Production Rates")
        self._create_price_list(name="Staging Rates")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?filter[name]=Production&filter[name]=Staging", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        names = [r["name"] for r in results]
        self.assertIn("Production Rates", names)
        self.assertIn("Staging Rates", names)

    def test_filter_by_name_repeated_params_one_match(self):
        """Test OR filtering with repeated bracket params where only one value matches."""
        self._create_price_list(name="Production Rates")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?filter[name]=Production&filter[name]=Nonexistent", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        matching = [r for r in results if r["name"] == "Production Rates"]
        self.assertEqual(len(matching), 1)

    def test_filter_by_enabled_true(self):
        """Test filtering for enabled price lists."""
        self._create_price_list(name="Enabled PL")
        self._create_price_list(name="Disabled PL", enabled=False)

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?filter[enabled]=true", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        for result in results:
            self.assertTrue(result["enabled"])

    def test_filter_by_enabled_false(self):
        """Test filtering for disabled price lists."""
        self._create_price_list(name="Enabled PL")
        self._create_price_list(name="Disabled PL", enabled=False)

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?filter[enabled]=false", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        for result in results:
            self.assertFalse(result["enabled"])

    def test_filter_enabled_omitted_returns_all(self):
        """Test that omitting enabled filter returns both enabled and disabled."""
        self._create_price_list(name="Enabled PL")
        self._create_price_list(name="Disabled PL", enabled=False)

        url = reverse("price-lists-list")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        enabled_values = {r["enabled"] for r in results}
        self.assertEqual(enabled_values, {True, False})

    def test_filter_by_currency(self):
        """Test filtering by currency."""
        self._create_price_list(name="USD PL", currency="USD")
        self._create_price_list(name="EUR PL", currency="EUR")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?filter[currency]=EUR", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        for result in results:
            self.assertEqual(result["currency"], "EUR")

    # --- Ordering (bracket notation) ---

    def test_order_by_name_asc(self):
        """Test ordering by name ascending."""
        self._create_price_list(name="Zebra Rates")
        self._create_price_list(name="Alpha Rates")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?order_by[name]=asc", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))

    def test_order_by_name_desc(self):
        """Test ordering by name descending."""
        self._create_price_list(name="Alpha Rates")
        self._create_price_list(name="Zebra Rates")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?order_by[name]=desc", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_order_by_effective_end_date(self):
        """Test ordering by effective_end_date."""
        self._create_price_list(name="Short PL", effective_end_date="2026-03-31")
        self._create_price_list(name="Long PL", effective_end_date="2026-12-31")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?order_by[effective_end_date]=asc", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        dates = [r["effective_end_date"] for r in results]
        self.assertEqual(dates, sorted(dates))

    def test_order_by_currency(self):
        """Test ordering by currency."""
        self._create_price_list(name="USD PL", currency="USD")
        self._create_price_list(name="EUR PL", currency="EUR")

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?order_by[currency]=asc", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_order_by_assigned_cost_model_count(self):
        """Test ordering by assigned cost model count."""
        create_response = self._create_price_list(name="Assigned PL")
        pl_uuid = create_response.data["uuid"]
        self._create_price_list(name="Unassigned PL")

        with tenant_context(self.tenant):
            cost_model = CostModel.objects.first()
            PriceListCostModelMap.objects.create(
                price_list_id=pl_uuid,
                cost_model=cost_model,
                priority=1,
            )

        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?order_by[assigned_cost_model_count]=desc", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- Query param validation ---

    def test_unknown_query_param_returns_400(self):
        """Test that unknown query params return 400."""
        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?foo=bar", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_filter_param_returns_400(self):
        """Test that unknown filter params return 400."""
        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?filter[invalid_field]=value", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_ordering_field_returns_400(self):
        """Test that ordering by invalid field returns 400."""
        url = reverse("price-lists-list")
        response = self.client.get(f"{url}?order_by[nonexistent]=asc", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Affected cost models ---

    def test_affected_cost_models_none(self):
        """Test affected-cost-models returns empty list when not assigned."""
        create_response = self._create_price_list()
        pl_uuid = create_response.data["uuid"]

        affected_url = reverse("price-lists-affected-cost-models", kwargs={"uuid": pl_uuid})
        response = self.client.get(affected_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_affected_cost_models_returns_linked(self):
        """Test affected-cost-models returns cost models linked to this price list."""
        create_response = self._create_price_list()
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

    # --- Inline assigned cost models ---

    def test_inline_assigned_cost_models_in_response(self):
        """Test that list response includes assigned cost model data inline."""
        create_response = self._create_price_list()
        pl_uuid = create_response.data["uuid"]

        with tenant_context(self.tenant):
            cost_model = CostModel.objects.first()
            PriceListCostModelMap.objects.create(
                price_list_id=pl_uuid,
                cost_model=cost_model,
                priority=1,
            )

        url = reverse("price-lists-list")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        pl_result = next(r for r in results if r["uuid"] == pl_uuid)
        self.assertEqual(pl_result["assigned_cost_model_count"], 1)
        self.assertEqual(len(pl_result["assigned_cost_models"]), 1)
        self.assertEqual(pl_result["assigned_cost_models"][0]["uuid"], str(cost_model.uuid))

    def test_inline_assigned_cost_model_count_zero(self):
        """Test that unassigned price list has count 0."""
        create_response = self._create_price_list()

        self.assertEqual(create_response.data["assigned_cost_model_count"], 0)
        self.assertEqual(create_response.data["assigned_cost_models"], [])

    # --- Duplicate ---

    def test_duplicate_price_list(self):
        """Test duplicating a price list."""
        create_response = self._create_price_list(name="Original PL")
        pl_uuid = create_response.data["uuid"]

        dup_url = reverse("price-lists-duplicate", kwargs={"uuid": pl_uuid})
        response = self.client.post(dup_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Copy of Original PL")
        self.assertEqual(response.data["version"], 1)
        self.assertEqual(response.data["enabled"], True)
        self.assertNotEqual(response.data["uuid"], pl_uuid)
        self.assertEqual(response.data["currency"], create_response.data["currency"])
        self.assertEqual(response.data["effective_start_date"], create_response.data["effective_start_date"])
        self.assertEqual(response.data["effective_end_date"], create_response.data["effective_end_date"])

    def test_duplicate_not_assigned_to_cost_models(self):
        """Test that duplicated price list is not assigned to any cost models."""
        create_response = self._create_price_list()
        pl_uuid = create_response.data["uuid"]

        with tenant_context(self.tenant):
            cost_model = CostModel.objects.first()
            PriceListCostModelMap.objects.create(
                price_list_id=pl_uuid,
                cost_model=cost_model,
                priority=1,
            )

        dup_url = reverse("price-lists-duplicate", kwargs={"uuid": pl_uuid})
        response = self.client.post(dup_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["assigned_cost_model_count"], 0)
        self.assertEqual(response.data["assigned_cost_models"], [])

    def test_duplicate_long_name_truncated(self):
        """Test that duplicate truncates name if too long."""
        long_name = "A" * 255
        create_response = self._create_price_list(name=long_name)
        pl_uuid = create_response.data["uuid"]

        dup_url = reverse("price-lists-duplicate", kwargs={"uuid": pl_uuid})
        response = self.client.post(dup_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["name"].startswith("Copy of "))
        self.assertLessEqual(len(response.data["name"]), 255)

    def test_duplicate_nonexistent_returns_404(self):
        """Test that duplicating a nonexistent price list returns 404."""
        dup_url = reverse("price-lists-duplicate", kwargs={"uuid": "00000000-0000-0000-0000-000000000099"})
        response = self.client.post(dup_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
