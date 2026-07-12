#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Price List views."""
import logging
from unittest.mock import MagicMock
from unittest.mock import patch

from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate


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

    def test_create_price_list_rates_include_metric_labels(self):
        """Test that rates include label_metric, label_measurement, label_measurement_unit."""
        response = self._create_price_list()
        rates = response.data["rates"]
        self.assertTrue(len(rates) > 0)
        metric = rates[0]["metric"]
        self.assertEqual(metric["label_metric"], "CPU")
        self.assertEqual(metric["label_measurement"], "Usage")
        self.assertEqual(metric["label_measurement_unit"], "core-hours")

        detail_url = reverse("price-lists-detail", kwargs={"uuid": response.data["uuid"]})
        get_response = self.client.get(detail_url, **self.headers)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        get_metric = get_response.data["rates"][0]["metric"]
        self.assertEqual(get_metric["label_metric"], "CPU")
        self.assertEqual(get_metric["label_measurement"], "Usage")
        self.assertEqual(get_metric["label_measurement_unit"], "core-hours")

    @patch("cost_models.price_list_serializer.metric_constants.get_cost_model_metrics_map")
    def test_metric_labels_error_on_corrupted_map(self, mock_map):
        """Test that corrupted metric map returns 500."""
        mock_map.return_value = {"cpu_core_usage_per_hour": {"source_type": "OCP"}}
        url = reverse("price-lists-list")
        response = self.client.post(url, data=self.price_list_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_create_price_list_duplicate_custom_name_fails(self):
        """Test that duplicate custom_name in rates fails."""
        url = reverse("price-lists-list")
        data = self.price_list_data.copy()
        data["rates"] = [
            {
                "metric": {"name": "cpu_core_usage_per_hour"},
                "custom_name": "my_rate",
                "tiered_rates": [{"value": "1.50", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}],
                "cost_type": "Infrastructure",
            },
            {
                "metric": {"name": "memory_gb_usage_per_hour"},
                "custom_name": "my_rate",
                "tiered_rates": [{"value": "2.00", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}],
                "cost_type": "Infrastructure",
            },
        ]
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Duplicate custom_name", str(response.data))

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

    def _create_price_list_no_usage(self):
        """Helper: create a price list without usage in tiered_rates (matches real client behavior)."""
        url = reverse("price-lists-list")
        post_data = {
            "rates": [
                {
                    "cost_type": "Infrastructure",
                    "custom_name": "a test",
                    "description": "",
                    "metric": {"name": "cpu_core_effective_usage_per_hour"},
                    "tiered_rates": [{"unit": "USD", "value": 1}],
                }
            ],
            "currency": "USD",
            "description": "",
            "effective_end_date": "2026-06-30",
            "effective_start_date": "2026-05-01",
            "name": "pedro_test",
        }
        resp = self.client.post(url, data=post_data, format="json", **self.headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["version"], 1)
        return resp

    def test_normalize_tiered_rate_creates_usage_when_values_provided(self):
        """Test that usage dict is created when usage_start/usage_end have real values."""
        from cost_models.serializers import RateSerializer

        rate = {"value": "1.00", "unit": "USD", "usage_start": "0", "usage_end": "100"}
        RateSerializer._normalize_tiered_rate(rate)
        self.assertIn("usage", rate)
        self.assertNotIn("usage_start", rate)
        self.assertNotIn("usage_end", rate)

    def test_update_metadata_does_not_increment_version(self):
        """Test that metadata-only updates do not increment version."""
        create_response = self._create_price_list_no_usage()
        pl_uuid = create_response.data["uuid"]
        self.assertEqual(create_response.data["version"], 1)

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})

        update_data = dict(create_response.data)
        update_data["name"] = "Renamed"
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], 1)

        update_data = dict(response.data)
        update_data["description"] = "new desc"
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], 1)

        update_data = dict(response.data)
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], 1)

        update_data = dict(response.data)
        update_data["rates"] = [dict(r) for r in update_data["rates"]]
        update_data["rates"][0]["description"] = "updated rate description"
        response = self.client.put(detail_url, data=update_data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version"], 1)

        with tenant_context(self.tenant):
            rate = Rate.objects.get(price_list__uuid=pl_uuid)
            self.assertEqual(rate.description, "updated rate description")

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

    def test_reenable_disabled_price_list(self):
        """Test that a disabled price list can be re-enabled with only enabled=True."""
        create_response = self._create_price_list()
        pl_uuid = create_response.data["uuid"]

        detail_url = reverse("price-lists-detail", kwargs={"uuid": pl_uuid})
        self.client.put(detail_url, data={**self.price_list_data, "enabled": False}, format="json", **self.headers)

        response = self.client.put(detail_url, data={"enabled": True}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["enabled"])

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


class PriceListRatesUnitTest(IamTestCase):
    """T1 Unit tests for RateFilter, lazy sync, and response building (TC-100..TC-117)."""

    DIVERSE_RATES = [
        {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "custom_name": "CPU Usage Rate",
            "tiered_rates": [{"value": "1.50", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "cpu_core_request_per_hour"},
            "custom_name": "CPU Request Rate",
            "tiered_rates": [{"value": "2.00", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "memory_gb_usage_per_hour"},
            "custom_name": "Memory Usage Rate",
            "tiered_rates": [{"value": "0.50", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "storage_gb_usage_per_month"},
            "custom_name": "Storage Usage Rate",
            "tiered_rates": [{"value": "0.10", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}],
            "cost_type": "Supplementary",
        },
        {
            "metric": {"name": "node_cost_per_month"},
            "custom_name": "Node Count Rate",
            "tiered_rates": [{"value": "100.00", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}],
            "cost_type": "Infrastructure",
        },
        {
            "metric": {"name": "cpu_core_usage_per_hour"},
            "custom_name": "CPU Tag Rate",
            "tag_rates": {
                "tag_key": "environment",
                "tag_values": [
                    {"tag_value": "production", "value": "3.00", "unit": "USD", "default": False, "description": ""}
                ],
            },
            "cost_type": "Supplementary",
        },
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _create_diverse_price_list(self):
        """Create a price list with diverse rates via API."""
        url = reverse("price-lists-list")
        data = {
            "name": "Diverse Rates PL",
            "description": "Price list with diverse rate types",
            "currency": "USD",
            "effective_start_date": "2026-01-01",
            "effective_end_date": "2026-12-31",
            "rates": self.DIVERSE_RATES,
        }
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data["uuid"]

    def _get_rate_queryset(self, pl_uuid):
        """Get Rate queryset for a price list within tenant context."""
        with tenant_context(self.tenant):
            return Rate.objects.filter(price_list_id=pl_uuid)

    def _apply_rate_filter(self, pl_uuid, query_string, schema_name=None):
        """Instantiate RateFilter with proper form initialization and return filtered qs."""
        from django.http import QueryDict

        from cost_models.price_list_view import RateFilter

        qs = Rate.objects.filter(price_list_id=pl_uuid)
        request = MagicMock()
        request.query_params = QueryDict(query_string)
        if schema_name:
            request.user.customer.schema_name = schema_name
        f = RateFilter(data={}, queryset=qs, request=request)
        f.form.is_valid()
        return f.filter_queryset(qs), f, request

    # --- TC-100: RateFilter metric_type filters queryset ---

    def test_rate_filter_metric_type_filters_queryset(self):
        """TC-100/BAC-31: RateFilter with metric_type=cpu returns only CPU Rate rows."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[metric_type]=cpu")
            self.assertTrue(result.exists())
            for rate in result:
                self.assertEqual(rate.metric_type, "cpu")

    # --- TC-101: RateFilter metric_type case insensitive ---

    def test_rate_filter_metric_type_case_insensitive(self):
        """TC-101/BAC-31: metric_type=CPU matches cpu stored value."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[metric_type]=CPU")
            self.assertTrue(result.exists())
            for rate in result:
                self.assertEqual(rate.metric_type, "cpu")

    # --- TC-102: RateFilter name icontains ---

    def test_rate_filter_name_icontains(self):
        """TC-102/BAC-33: name=usage returns rates with 'usage' in custom_name."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[name]=usage")
            self.assertTrue(result.exists())
            for rate in result:
                self.assertIn("usage", rate.custom_name.lower())

    # --- TC-103: RateFilter name partial match ---

    def test_rate_filter_name_partial_match(self):
        """TC-103/BAC-33: name=CPU matches 'CPU Usage Rate' and 'CPU Request Rate'."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[name]=CPU")
            self.assertGreaterEqual(result.count(), 2)

    # --- TC-104: RateFilter cost_type iexact ---

    def test_rate_filter_cost_type_iexact(self):
        """TC-104/BAC-34: cost_type=infrastructure matches 'Infrastructure'."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[cost_type]=infrastructure")
            self.assertTrue(result.exists())
            for rate in result:
                self.assertEqual(rate.cost_type, "Infrastructure")

    # --- TC-105: RateFilter measurement maps to metrics ---

    def test_rate_filter_measurement_maps_to_metrics(self):
        """TC-105/BAC-32: filter_measurement with 'usage' returns rates with usage metrics."""
        pl_uuid = self._create_diverse_price_list()
        usage_metrics = {"cpu_core_usage_per_hour", "memory_gb_usage_per_hour", "storage_gb_usage_per_month"}
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[measurement]=usage", schema_name=self.schema_name)
            self.assertTrue(result.exists())
            for rate in result:
                self.assertIn(rate.metric, usage_metrics)

    # --- TC-106: RateFilter measurement case insensitive ---

    def test_rate_filter_measurement_case_insensitive(self):
        """TC-106/BAC-32: filter_measurement with 'USAGE' matches same as 'usage'."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result_lower, _, _ = self._apply_rate_filter(
                pl_uuid, "filter[measurement]=usage", schema_name=self.schema_name
            )
            result_upper, _, _ = self._apply_rate_filter(
                pl_uuid, "filter[measurement]=USAGE", schema_name=self.schema_name
            )
            uuids_lower = set(result_lower.values_list("uuid", flat=True))
            uuids_upper = set(result_upper.values_list("uuid", flat=True))
            self.assertEqual(uuids_lower, uuids_upper)

    # --- TC-107: RateFilter measurement unknown returns empty ---

    def test_rate_filter_measurement_unknown_returns_empty(self):
        """TC-107/BAC-32: filter_measurement with 'invalid' returns empty queryset."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(
                pl_uuid, "filter[measurement]=invalid", schema_name=self.schema_name
            )
            self.assertEqual(result.count(), 0)

    # --- TC-108: RateFilter measurement uses schema-aware map ---

    @patch("cost_models.price_list_view.metric_constants.get_cost_model_metrics_map")
    def test_rate_filter_measurement_uses_schema_aware_map(self, mock_get_map):
        """TC-108/BAC-48: filter_measurement calls get_cost_model_metrics_map(schema=schema)."""
        mock_get_map.return_value = metric_constants.COST_MODEL_METRIC_MAP
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            self._apply_rate_filter(pl_uuid, "filter[measurement]=usage", schema_name=self.schema_name)
            mock_get_map.assert_called_with(schema=self.schema_name)

    # --- TC-109: RateFilter multi-value OR CSV ---

    def test_rate_filter_multi_value_or_csv(self):
        """TC-109/BAC-35: metric_type=cpu,memory returns both CPU and memory rates."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[metric_type]=cpu,memory")
            types = set(result.values_list("metric_type", flat=True))
            self.assertIn("cpu", types)
            self.assertIn("memory", types)

    # --- TC-110: RateFilter multi-value OR repeated params ---

    def test_rate_filter_multi_value_or_repeated(self):
        """TC-110/BAC-35: metric_type=cpu&metric_type=memory returns both types."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[metric_type]=cpu&filter[metric_type]=memory")
            types = set(result.values_list("metric_type", flat=True))
            self.assertIn("cpu", types)
            self.assertIn("memory", types)

    # --- TC-111: RateFilter combined fields AND ---

    def test_rate_filter_combined_fields_and(self):
        """TC-111/BAC-36: metric_type=cpu + cost_type=Infrastructure returns intersection."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            result, _, _ = self._apply_rate_filter(pl_uuid, "filter[metric_type]=cpu&filter[cost_type]=Infrastructure")
            self.assertTrue(result.exists())
            for rate in result:
                self.assertEqual(rate.metric_type, "cpu")
                self.assertEqual(rate.cost_type, "Infrastructure")

    # --- TC-112: _ensure_rate_sync triggers when rate_id missing ---

    @patch("cost_models.price_list_view.sync_rate_table")
    def test_ensure_rate_sync_triggers_when_rate_id_missing(self, mock_sync):
        """TC-112/BAC-44: _ensure_rate_sync calls sync_rate_table when JSON lacks rate_id."""
        from cost_models.price_list_view import PriceListViewSet

        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            pl = PriceList.objects.get(uuid=pl_uuid)
            for entry in pl.rates:
                entry.pop("rate_id", None)
            pl.save(update_fields=["rates"])
            pl.refresh_from_db()

        view = PriceListViewSet()
        with tenant_context(self.tenant):
            pl = PriceList.objects.get(uuid=pl_uuid)
            view._ensure_rate_sync(pl)
            mock_sync.assert_called_once()

    # --- TC-113: _ensure_rate_sync skips when rate_id present ---

    @patch("cost_models.price_list_view.sync_rate_table")
    def test_ensure_rate_sync_skips_when_rate_id_present(self, mock_sync):
        """TC-113/BAC-44: _ensure_rate_sync does NOT call sync_rate_table when all entries have rate_id."""
        from cost_models.price_list_view import PriceListViewSet

        pl_uuid = self._create_diverse_price_list()
        view = PriceListViewSet()
        with tenant_context(self.tenant):
            pl = PriceList.objects.get(uuid=pl_uuid)
            self.assertTrue(all("rate_id" in e for e in pl.rates))
            view._ensure_rate_sync(pl)
            mock_sync.assert_not_called()

    # --- TC-114: _ensure_rate_sync skips empty rates ---

    @patch("cost_models.price_list_view.sync_rate_table")
    def test_ensure_rate_sync_skips_empty_rates(self, mock_sync):
        """TC-114/BAC-44: _ensure_rate_sync returns immediately for empty/None rates."""
        from cost_models.price_list_view import PriceListViewSet

        view = PriceListViewSet()
        pl = MagicMock()
        pl.rates = []
        view._ensure_rate_sync(pl)
        mock_sync.assert_not_called()

        pl.rates = None
        view._ensure_rate_sync(pl)
        mock_sync.assert_not_called()

    # --- TC-115: _build_rate_response enriches labels ---

    def test_build_rate_response_enriches_labels(self):
        """TC-115/BAC-49: _build_rate_response adds label_metric, label_measurement, label_measurement_unit."""
        from cost_models.price_list_view import PriceListViewSet

        pl_uuid = self._create_diverse_price_list()
        view = PriceListViewSet()
        with tenant_context(self.tenant):
            pl = PriceList.objects.get(uuid=pl_uuid)
            filtered_qs = Rate.objects.filter(price_list=pl)
            result = view._build_rate_response(pl, filtered_qs, self.schema_name)

        self.assertTrue(len(result) > 0)
        for rate_dict in result:
            metric = rate_dict.get("metric", {})
            self.assertIn("label_metric", metric, f"Missing label_metric in {rate_dict}")
            self.assertIn("label_measurement", metric, f"Missing label_measurement in {rate_dict}")
            self.assertIn("label_measurement_unit", metric, f"Missing label_measurement_unit in {rate_dict}")

    # --- TC-116: _build_rate_response includes tiered_rates from JSON ---

    def test_build_rate_response_includes_tiered_rates_from_json(self):
        """TC-116/BAC-49: Result includes full tiered_rates ladder from JSON cross-reference."""
        from cost_models.price_list_view import PriceListViewSet

        pl_uuid = self._create_diverse_price_list()
        view = PriceListViewSet()
        with tenant_context(self.tenant):
            pl = PriceList.objects.get(uuid=pl_uuid)
            tiered_rate = Rate.objects.filter(price_list=pl, tag_key="")
            result = view._build_rate_response(pl, tiered_rate, self.schema_name)

        tiered_results = [r for r in result if "tiered_rates" in r]
        self.assertTrue(len(tiered_results) > 0, "No tiered rates found in response")
        for rate_dict in tiered_results:
            self.assertIsInstance(rate_dict["tiered_rates"], list)
            self.assertTrue(len(rate_dict["tiered_rates"]) > 0)

    # --- TC-117: _build_rate_response includes tag_rates from JSON ---

    def test_build_rate_response_includes_tag_rates_from_json(self):
        """TC-117/BAC-42: Result includes full tag_rates structure from JSON cross-reference."""
        from cost_models.price_list_view import PriceListViewSet

        pl_uuid = self._create_diverse_price_list()
        view = PriceListViewSet()
        with tenant_context(self.tenant):
            pl = PriceList.objects.get(uuid=pl_uuid)
            tag_rate = Rate.objects.filter(price_list=pl).exclude(tag_key="")
            self.assertTrue(tag_rate.exists(), "No tag rate rows found")
            result = view._build_rate_response(pl, tag_rate, self.schema_name)

        tag_results = [r for r in result if "tag_rates" in r]
        self.assertTrue(len(tag_results) > 0, "No tag rates found in response")
        for rate_dict in tag_results:
            self.assertIn("tag_key", rate_dict["tag_rates"])
            self.assertIn("tag_values", rate_dict["tag_rates"])


class PriceListRatesIntegrationTest(IamTestCase):
    """T2 Integration tests: full HTTP wiring for the rates sub-endpoint (TC-120..TC-126)."""

    DIVERSE_RATES = PriceListRatesUnitTest.DIVERSE_RATES

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _create_diverse_price_list(self):
        """Create a price list with diverse rates via API and return its UUID."""
        url = reverse("price-lists-list")
        data = {
            "name": "Integration PL",
            "description": "For integration tests",
            "currency": "USD",
            "effective_start_date": "2026-01-01",
            "effective_end_date": "2026-12-31",
            "rates": self.DIVERSE_RATES,
        }
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data["uuid"]

    # --- TC-120: Rates endpoint returns paginated envelope ---

    def test_rates_endpoint_returns_paginated_envelope(self):
        """TC-120/BAC-37: GET /price-lists/{uuid}/rates/ returns {meta, links, data}."""
        pl_uuid = self._create_diverse_price_list()
        url = reverse("price-lists-rates", kwargs={"uuid": pl_uuid})
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("meta", response.data)
        self.assertIn("links", response.data)
        self.assertIn("data", response.data)
        self.assertEqual(response.data["meta"]["count"], len(self.DIVERSE_RATES))

    # --- TC-121: Rates endpoint filters by metric_type via HTTP ---

    def test_rates_endpoint_filters_metric_type_via_http(self):
        """TC-121/BAC-31: HTTP filter[metric_type]=cpu returns only CPU rates."""
        pl_uuid = self._create_diverse_price_list()
        url = reverse("price-lists-rates", kwargs={"uuid": pl_uuid})
        response = self.client.get(url, {"filter[metric_type]": "cpu"}, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for rate in response.data["data"]:
            self.assertEqual(rate["metric_type"], "cpu")
        self.assertGreater(len(response.data["data"]), 0)

    # --- TC-122: Rates endpoint respects limit/offset pagination ---

    def test_rates_endpoint_respects_pagination(self):
        """TC-122/BAC-37: limit=2&offset=0 returns at most 2 rates."""
        pl_uuid = self._create_diverse_price_list()
        url = reverse("price-lists-rates", kwargs={"uuid": pl_uuid})
        response = self.client.get(url, {"limit": "2", "offset": "0"}, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data["data"]), 2)
        self.assertEqual(response.data["meta"]["count"], len(self.DIVERSE_RATES))

    # --- TC-123: Rates endpoint supports order_by ---

    def test_rates_endpoint_supports_order_by(self):
        """TC-123/BAC-38: order_by[name]=asc returns rates sorted by custom_name."""
        pl_uuid = self._create_diverse_price_list()
        url = reverse("price-lists-rates", kwargs={"uuid": pl_uuid})
        response = self.client.get(url, {"order_by[name]": "asc"}, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["custom_name"] for r in response.data["data"]]
        self.assertEqual(names, sorted(names))

    # --- TC-124: Lazy sync triggered via HTTP when rate_id missing ---

    @patch("cost_models.price_list_view.sync_rate_table")
    def test_lazy_sync_triggered_via_http(self, mock_sync):
        """TC-124/BAC-44: HTTP request triggers sync when JSON lacks rate_id."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            pl = PriceList.objects.get(uuid=pl_uuid)
            for entry in pl.rates:
                entry.pop("rate_id", None)
            pl.save(update_fields=["rates"])

        url = reverse("price-lists-rates", kwargs={"uuid": pl_uuid})
        self.client.get(url, **self.headers)
        mock_sync.assert_called_once()

    # --- TC-125: cost_model list filter via HTTP ---

    def test_cost_model_list_filter_via_http(self):
        """TC-125/BAC-50: filter[cost_model]=<uuid> returns only matching price lists."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            cost_model = CostModel.objects.first()
            PriceListCostModelMap.objects.create(
                price_list_id=pl_uuid,
                cost_model=cost_model,
                priority=1,
            )

        url = reverse("price-lists-list")
        response = self.client.get(url, {"filter[cost_model]": str(cost_model.uuid)}, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        uuids = [r["uuid"] for r in results]
        self.assertIn(pl_uuid, uuids)

    # --- TC-126: cost_model filter deduplication ---

    def test_cost_model_filter_no_duplicates(self):
        """TC-126/BAC-50: Multiple cost model maps do not produce duplicate price list rows."""
        pl_uuid = self._create_diverse_price_list()
        with tenant_context(self.tenant):
            cost_models = list(CostModel.objects.all()[:2])
            for idx, cm in enumerate(cost_models):
                PriceListCostModelMap.objects.create(
                    price_list_id=pl_uuid,
                    cost_model=cm,
                    priority=idx + 1,
                )

        url = reverse("price-lists-list")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        uuids = [r["uuid"] for r in results]
        self.assertEqual(len(uuids), len(set(uuids)), "Duplicate price lists in response")


class PriceListRatesBehavioralTest(IamTestCase):
    """T3 Behavioral tests: error paths and edge cases (TC-140..TC-144)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        logging.disable(0)

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _create_empty_price_list(self):
        """Create a price list with no rates."""
        url = reverse("price-lists-list")
        data = {
            "name": "Empty PL",
            "description": "No rates",
            "currency": "USD",
            "effective_start_date": "2026-01-01",
            "effective_end_date": "2026-12-31",
            "rates": [],
        }
        response = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data["uuid"]

    # --- TC-140: Invalid filter param returns 400 ---

    def test_invalid_filter_param_returns_400(self):
        """TC-140/SI-10: filter[invalid_field]=x returns 400."""
        url = reverse("price-lists-list")
        data = {
            "name": "PL for 400 test",
            "description": "test",
            "currency": "USD",
            "effective_start_date": "2026-01-01",
            "effective_end_date": "2026-12-31",
            "rates": [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [
                        {"value": "1.00", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}
                    ],
                    "cost_type": "Infrastructure",
                }
            ],
        }
        create_resp = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        pl_uuid = create_resp.data["uuid"]

        rates_url = reverse("price-lists-rates", kwargs={"uuid": pl_uuid})
        response = self.client.get(rates_url, {"filter[bogus]": "x"}, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- TC-141: Nonexistent price list returns 404 ---

    def test_rates_nonexistent_price_list_returns_404(self):
        """TC-141/AC-6: GET /price-lists/<bad-uuid>/rates/ returns 404."""
        url = reverse("price-lists-rates", kwargs={"uuid": "00000000-0000-0000-0000-000000000099"})
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- TC-142: Rates endpoint has RBAC permission configured ---

    def test_rates_endpoint_has_rbac_permission(self):
        """TC-142/AC-6: PriceListViewSet has CostModelsAccessPermission configured."""
        from api.common.permissions.cost_models_access import CostModelsAccessPermission
        from cost_models.price_list_view import PriceListViewSet

        self.assertIn(CostModelsAccessPermission, PriceListViewSet.permission_classes)

    # --- TC-143: Empty price list rates returns empty data ---

    def test_rates_empty_price_list_returns_empty(self):
        """TC-143/BAC-40: A price list with no rates returns {data: [], meta: {count: 0}}."""
        pl_uuid = self._create_empty_price_list()
        url = reverse("price-lists-rates", kwargs={"uuid": pl_uuid})
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"], [])
        self.assertEqual(response.data["meta"]["count"], 0)

    # --- TC-144: cost_model filter with non-matching UUID returns no results ---

    def test_cost_model_filter_no_match_returns_empty(self):
        """TC-144/BAC-50: cost_model filter with unassigned UUID returns 0 price lists."""
        url = reverse("price-lists-list")
        response = self.client.get(url, {"filter[cost_model]": "00000000-0000-0000-0000-000000000099"}, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", []))
        self.assertEqual(len(results), 0)

    # --- TC-145: cost_model filter with malformed UUID returns 400 ---

    def test_cost_model_filter_malformed_uuid_returns_400(self):
        """TC-145/SI-10: filter[cost_model]=not-a-uuid returns 400, not 500."""
        url = reverse("price-lists-list")
        response = self.client.get(url, {"filter[cost_model]": "not-a-uuid"}, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- TC-146: rates endpoint rejects unknown top-level params ---

    def test_rates_unknown_top_level_param_returns_400(self):
        """TC-146/SI-10: GET /rates/?bogus=bogus returns 400."""
        url = reverse("price-lists-list")
        data = {
            "name": "PL for param test",
            "description": "test",
            "currency": "USD",
            "effective_start_date": "2026-01-01",
            "effective_end_date": "2026-12-31",
            "rates": [
                {
                    "metric": {"name": "cpu_core_usage_per_hour"},
                    "tiered_rates": [
                        {"value": "1.00", "unit": "USD", "usage": {"usage_start": None, "usage_end": None}}
                    ],
                    "cost_type": "Infrastructure",
                }
            ],
        }
        create_resp = self.client.post(url, data=data, format="json", **self.headers)
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        pl_uuid = create_resp.data["uuid"]

        rates_url = reverse("price-lists-rates", kwargs={"uuid": pl_uuid})
        response = self.client.get(rates_url, {"bogus": "bogus"}, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
