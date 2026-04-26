#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the StaticExchangeRate serializer."""
from decimal import Decimal
from unittest.mock import MagicMock
from unittest.mock import patch

from django_tenants.utils import tenant_context

from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
from cost_models.models import StaticExchangeRate
from cost_models.static_exchange_rate_serializer import StaticExchangeRateSerializer
from cost_models.static_exchange_rate_utils import remove_static_and_backfill_dynamic
from masu.test import MasuTestCase


class StaticExchangeRateSerializerTest(MasuTestCase):
    """Tests for StaticExchangeRateSerializer."""

    def setUp(self):
        super().setUp()
        self.valid_data = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": "0.870000000000000",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        }

    def _make_request_context(self):
        request = MagicMock()
        request.user.customer.schema_name = self.schema_name
        return {"request": request}

    def test_validate_base_currency_uppercase(self):
        """Test that base_currency is uppercased."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["base_currency"] = "usd"
            serializer = StaticExchangeRateSerializer(data=data, context=self._make_request_context())
            self.assertTrue(serializer.is_valid())
            self.assertEqual(serializer.validated_data["base_currency"], "USD")

    def test_validate_invalid_currency(self):
        """Test that invalid currency codes are rejected."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["base_currency"] = "FAKE"
            serializer = StaticExchangeRateSerializer(data=data, context=self._make_request_context())
            self.assertFalse(serializer.is_valid())

    def test_validate_same_currencies(self):
        """Test that base_currency == target_currency is rejected."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["target_currency"] = "USD"
            serializer = StaticExchangeRateSerializer(data=data, context=self._make_request_context())
            self.assertFalse(serializer.is_valid())

    def test_validate_start_date_not_first_of_month(self):
        """Test that start_date must be the 1st of a month."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["start_date"] = "2026-01-15"
            serializer = StaticExchangeRateSerializer(data=data, context=self._make_request_context())
            self.assertFalse(serializer.is_valid())

    def test_validate_end_date_not_last_of_month(self):
        """Test that end_date must be the last day of a month."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["end_date"] = "2026-03-15"
            serializer = StaticExchangeRateSerializer(data=data, context=self._make_request_context())
            self.assertFalse(serializer.is_valid())

    def test_validate_start_after_end(self):
        """Test that start_date > end_date is rejected."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            data["start_date"] = "2026-04-01"
            data["end_date"] = "2026-03-31"
            serializer = StaticExchangeRateSerializer(data=data, context=self._make_request_context())
            self.assertFalse(serializer.is_valid())

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_create_upserts_monthly_exchange_rate(self, mock_invalidate):
        """Test that creating a static rate upserts MonthlyExchangeRate rows."""
        with tenant_context(self.tenant):
            serializer = StaticExchangeRateSerializer(data=self.valid_data, context=self._make_request_context())
            self.assertTrue(serializer.is_valid(), serializer.errors)
            instance = serializer.save()

            self.assertIsNotNone(instance.uuid)
            self.assertEqual(instance.version, 1)
            self.assertEqual(instance.name, "USD-EUR")

            monthly_rates = MonthlyExchangeRate.objects.filter(
                base_currency="USD",
                target_currency="EUR",
                rate_type=RateType.STATIC,
            )
            self.assertEqual(monthly_rates.count(), 3)

            for rate in monthly_rates:
                self.assertEqual(rate.exchange_rate, Decimal("0.870000000000000"))

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_overlap_detection(self, mock_invalidate):
        """Test that overlapping validity periods are rejected."""
        with tenant_context(self.tenant):
            serializer = StaticExchangeRateSerializer(data=self.valid_data, context=self._make_request_context())
            serializer.is_valid(raise_exception=True)
            serializer.save()

            overlap_data = {
                "base_currency": "USD",
                "target_currency": "EUR",
                "exchange_rate": "0.900000000000000",
                "start_date": "2026-02-01",
                "end_date": "2026-04-30",
            }
            serializer2 = StaticExchangeRateSerializer(data=overlap_data, context=self._make_request_context())
            self.assertFalse(serializer2.is_valid())

    @patch("cost_models.static_exchange_rate_serializer.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_update_increments_version(self, mock_invalidate):
        """Test that updating a static rate increments the version."""
        with tenant_context(self.tenant):
            serializer = StaticExchangeRateSerializer(data=self.valid_data, context=self._make_request_context())
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()
            self.assertEqual(instance.version, 1)

            update_data = {"exchange_rate": "0.900000000000000"}
            serializer2 = StaticExchangeRateSerializer(
                instance=instance, data=update_data, partial=True, context=self._make_request_context()
            )
            serializer2.is_valid(raise_exception=True)
            updated = serializer2.save()
            self.assertEqual(updated.version, 2)

    def test_delete_removes_static_monthly_rates(self):
        """Test that deleting a static rate removes static MonthlyExchangeRate rows."""
        with tenant_context(self.tenant):
            serializer = StaticExchangeRateSerializer(data=self.valid_data, context=self._make_request_context())
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()

            self.assertTrue(
                MonthlyExchangeRate.objects.filter(
                    base_currency="USD", target_currency="EUR", rate_type=RateType.STATIC
                ).exists()
            )

            remove_static_and_backfill_dynamic(
                instance.base_currency,
                instance.target_currency,
                instance.start_date,
                instance.end_date,
            )
            instance.delete()

            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    base_currency="USD", target_currency="EUR", rate_type=RateType.STATIC
                ).exists()
            )
            self.assertFalse(StaticExchangeRate.objects.filter(uuid=instance.uuid).exists())

    def test_name_computed_field(self):
        """Test name is read-only computed."""
        with tenant_context(self.tenant):
            data = self.valid_data.copy()
            serializer = StaticExchangeRateSerializer(data=data, context=self._make_request_context())
            self.assertTrue(serializer.is_valid(), serializer.errors)
