#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for monthly_exchange_rate_utils MonthlyExchangeRate side effects."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django_tenants.utils import tenant_context

from api.utils import DateHelper
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
from cost_models.models import StaticExchangeRate
from cost_models.monthly_exchange_rate_utils import remove_static_and_backfill_dynamic
from cost_models.monthly_exchange_rate_utils import upsert_static_monthly_rates
from masu.test import MasuTestCase


class UpsertStaticMonthlyRatesTest(MasuTestCase):
    """Tests for upsert_static_monthly_rates."""

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.all().delete()
            StaticExchangeRate.objects.all().delete()

    def test_single_month_creates_forward_and_inverse(self):
        """A one-month static rate should create both forward and inverse MonthlyExchangeRate rows."""
        with tenant_context(self.tenant):
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )
            upsert_static_monthly_rates(static_rate)

            forward = MonthlyExchangeRate.objects.get(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
            )
            self.assertEqual(forward.exchange_rate, Decimal("0.920000000000000"))
            self.assertEqual(forward.rate_type, RateType.STATIC)

            inverse = MonthlyExchangeRate.objects.get(
                effective_date=date(2026, 7, 1),
                base_currency="EUR",
                target_currency="USD",
            )
            expected_inverse = Decimal(1) / Decimal("0.920000000000000")
            self.assertAlmostEqual(float(inverse.exchange_rate), float(expected_inverse), places=10)
            self.assertEqual(inverse.rate_type, RateType.STATIC)

    def test_multi_month_range_only_writes_current_month(self):
        """A multi-month static rate should only create a MonthlyExchangeRate row for the current month."""
        with tenant_context(self.tenant):
            current_month = DateHelper().this_month_start.date()
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="GBP",
                exchange_rate=Decimal("0.780000000000000"),
                start_date=current_month,
                end_date=current_month.replace(month=current_month.month + 2),
            )
            upsert_static_monthly_rates(static_rate)

            months = MonthlyExchangeRate.objects.filter(base_currency="USD", target_currency="GBP").order_by(
                "effective_date"
            )
            self.assertEqual(months.count(), 1)
            self.assertEqual(months.first().effective_date, current_month)

    def test_inverse_not_written_when_explicit_reverse_exists(self):
        """Inverse row should not be written when an explicit StaticExchangeRate defines the reverse."""
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.create(
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.100000000000000"),
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )
            upsert_static_monthly_rates(static_rate)

            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    effective_date=date(2026, 7, 1),
                    base_currency="EUR",
                    target_currency="USD",
                ).exists()
            )

    def test_overwrites_dynamic_with_static(self):
        """Static upsert should overwrite existing dynamic MonthlyExchangeRate rows."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.870000000000000"),
                rate_type=RateType.DYNAMIC,
            )
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )
            upsert_static_monthly_rates(static_rate)

            rate = MonthlyExchangeRate.objects.get(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
            )
            self.assertEqual(rate.rate_type, RateType.STATIC)
            self.assertEqual(rate.exchange_rate, Decimal("0.920000000000000"))

    def test_zero_rate_raises_value_error(self):
        """A static rate with zero exchange_rate should raise ValueError."""
        with tenant_context(self.tenant):
            static_rate = StaticExchangeRate(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0"),
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )
            with self.assertRaises(ValueError):
                upsert_static_monthly_rates(static_rate)


class RemoveStaticAndBackfillDynamicTest(MasuTestCase):
    """Tests for remove_static_and_backfill_dynamic."""

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.all().delete()
            StaticExchangeRate.objects.all().delete()

    def test_removes_static_rows(self):
        """Removing a static rate should delete its MonthlyExchangeRate rows."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                rate_type=RateType.STATIC,
            )
            remove_static_and_backfill_dynamic("USD", "EUR", date(2026, 7, 1), date(2026, 7, 31))

            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    base_currency="USD", target_currency="EUR", rate_type=RateType.STATIC
                ).exists()
            )

    def test_removes_inverse_static_rows_when_no_explicit_reverse(self):
        """Auto-generated inverse static rows should also be removed."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                rate_type=RateType.STATIC,
            )
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 7, 1),
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.086956521739130"),
                rate_type=RateType.STATIC,
            )
            remove_static_and_backfill_dynamic("USD", "EUR", date(2026, 7, 1), date(2026, 7, 31))

            self.assertFalse(
                MonthlyExchangeRate.objects.filter(effective_date=date(2026, 7, 1), rate_type=RateType.STATIC).exists()
            )

    def test_preserves_inverse_when_explicit_reverse_exists(self):
        """Inverse static rows should be preserved when a separate StaticExchangeRate defines the reverse."""
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.create(
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.100000000000000"),
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 7, 1),
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.100000000000000"),
                rate_type=RateType.STATIC,
            )
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                rate_type=RateType.STATIC,
            )
            remove_static_and_backfill_dynamic("USD", "EUR", date(2026, 7, 1), date(2026, 7, 31))

            self.assertTrue(
                MonthlyExchangeRate.objects.filter(
                    effective_date=date(2026, 7, 1),
                    base_currency="EUR",
                    target_currency="USD",
                    rate_type=RateType.STATIC,
                ).exists()
            )

    @patch("cost_models.monthly_exchange_rate_utils.ExchangeRateDictionary")
    def test_backfills_dynamic_from_exchange_dictionary(self, mock_erd_cls):
        """After removing static rows, dynamic rates should be backfilled from ExchangeRateDictionary."""
        mock_erd = mock_erd_cls.objects.first.return_value
        mock_erd.currency_exchange_dictionary = {
            "USD": {"EUR": Decimal("0.870000000000000")},
            "EUR": {"USD": Decimal("1.149425287356322")},
        }

        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                rate_type=RateType.STATIC,
            )
            remove_static_and_backfill_dynamic("USD", "EUR", date(2026, 7, 1), date(2026, 7, 31))

            rate = MonthlyExchangeRate.objects.get(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
            )
            self.assertEqual(rate.rate_type, RateType.DYNAMIC)
            self.assertEqual(rate.exchange_rate, Decimal("0.870000000000000"))

    @patch("cost_models.monthly_exchange_rate_utils.ExchangeRateDictionary")
    def test_no_backfill_when_no_exchange_dictionary(self, mock_erd_cls):
        """No backfill should happen when ExchangeRateDictionary is empty."""
        mock_erd_cls.objects.first.return_value = None

        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 7, 1),
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.920000000000000"),
                rate_type=RateType.STATIC,
            )
            remove_static_and_backfill_dynamic("USD", "EUR", date(2026, 7, 1), date(2026, 7, 31))

            self.assertFalse(MonthlyExchangeRate.objects.filter(base_currency="USD", target_currency="EUR").exists())
