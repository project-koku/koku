#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for monthly_exchange_rate_utils MonthlyExchangeRate side effects."""
from decimal import Decimal
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django_tenants.utils import tenant_context

from api.currency.models import ExchangeRateDictionary
from cost_models.models import EnabledCurrency
from cost_models.models import MonthlyExchangeRate
from cost_models.models import RateType
from cost_models.models import StaticExchangeRate
from cost_models.monthly_exchange_rate_utils import _backfill_missing_past_months
from cost_models.monthly_exchange_rate_utils import populate_dynamic_monthly_rates
from cost_models.monthly_exchange_rate_utils import remove_monthly_rates
from cost_models.monthly_exchange_rate_utils import replace_static_to_dynamic_monthly_rates
from cost_models.monthly_exchange_rate_utils import upsert_static_monthly_rates
from masu.test import MasuTestCase


class UpsertStaticMonthlyRatesTest(MasuTestCase):
    """Tests for upsert_static_monthly_rates."""

    def setUp(self):
        super().setUp()
        self.month_start = self.dh.this_month_start.date()
        self.month_end = self.dh.this_month_end.date()
        ExchangeRateDictionary.objects.all().delete()
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.all().delete()
            StaticExchangeRate.objects.all().delete()
            EnabledCurrency.objects.all().delete()

    def test_single_month_creates_forward_only(self):
        """A one-month static rate should only create a forward STATIC MonthlyExchangeRate row."""
        with tenant_context(self.tenant):
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.92"),
                start_date=self.month_start,
                end_date=self.month_end,
            )
            upsert_static_monthly_rates(static_rate)

            forward = MonthlyExchangeRate.objects.get(
                effective_date=self.month_start,
                base_currency="USD",
                target_currency="EUR",
            )
            self.assertEqual(forward.exchange_rate, Decimal("0.92"))
            self.assertEqual(forward.rate_type, RateType.STATIC)

            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    effective_date=self.month_start,
                    base_currency="EUR",
                    target_currency="USD",
                ).exists(),
                "Inverse should not be auto-created; dynamic rates are populated by the daily Celery task.",
            )

    def test_does_not_overwrite_existing_dynamic_inverse(self):
        """Creating a static forward rate should not touch an existing dynamic inverse."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.15"),
                rate_type=RateType.DYNAMIC,
            )
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.92"),
                start_date=self.month_start,
                end_date=self.month_end,
            )
            upsert_static_monthly_rates(static_rate)

            inverse = MonthlyExchangeRate.objects.get(
                effective_date=self.month_start,
                base_currency="EUR",
                target_currency="USD",
            )
            self.assertEqual(inverse.exchange_rate, Decimal("1.15"))
            self.assertEqual(inverse.rate_type, RateType.DYNAMIC)

    def test_multi_month_range_only_writes_current_month(self):
        """A multi-month static rate should only create a MonthlyExchangeRate row for the current month."""
        with tenant_context(self.tenant):
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="GBP",
                exchange_rate=Decimal("0.78"),
                start_date=self.month_start,
                end_date=self.month_start + relativedelta(months=2),
            )
            upsert_static_monthly_rates(static_rate)

            months = MonthlyExchangeRate.objects.filter(base_currency="USD", target_currency="GBP").order_by(
                "effective_date"
            )
            self.assertEqual(months.count(), 1)
            self.assertEqual(months.first().effective_date, self.month_start)

    def test_no_inverse_even_when_explicit_reverse_exists(self):
        """No inverse row should be written even when a separate StaticExchangeRate defines the reverse."""
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.create(
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.10"),
                start_date=self.month_start,
                end_date=self.month_end,
            )
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.92"),
                start_date=self.month_start,
                end_date=self.month_end,
            )
            upsert_static_monthly_rates(static_rate)

            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    effective_date=self.month_start,
                    base_currency="EUR",
                    target_currency="USD",
                ).exists()
            )

    def test_overwrites_dynamic_with_static(self):
        """Static upsert should overwrite existing dynamic MonthlyExchangeRate rows."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.87"),
                rate_type=RateType.DYNAMIC,
            )
            static_rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.92"),
                start_date=self.month_start,
                end_date=self.month_end,
            )
            upsert_static_monthly_rates(static_rate)

            rate = MonthlyExchangeRate.objects.get(
                effective_date=self.month_start,
                base_currency="USD",
                target_currency="EUR",
            )
            self.assertEqual(rate.rate_type, RateType.STATIC)
            self.assertEqual(rate.exchange_rate, Decimal("0.92"))

    def test_zero_rate_raises_value_error(self):
        """A static rate with zero exchange_rate should raise ValueError."""
        with tenant_context(self.tenant):
            static_rate = StaticExchangeRate(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0"),
                start_date=self.month_start,
                end_date=self.month_end,
            )
            with self.assertRaises(ValueError):
                upsert_static_monthly_rates(static_rate)


class RemoveStaticAndBackfillDynamicTest(MasuTestCase):
    """Tests for replace_static_to_dynamic_monthly_rates."""

    def setUp(self):
        super().setUp()
        self.month_start = self.dh.this_month_start.date()
        self.month_end = self.dh.this_month_end.date()
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.all().delete()
            StaticExchangeRate.objects.all().delete()

    def test_removes_static_rows(self):
        """Removing a static rate should delete its MonthlyExchangeRate rows."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.92"),
                rate_type=RateType.STATIC,
            )
            replace_static_to_dynamic_monthly_rates("USD", "EUR", self.month_start, self.month_end)

            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    base_currency="USD", target_currency="EUR", rate_type=RateType.STATIC
                ).exists()
            )

    def test_removes_inverse_static_rows_when_no_explicit_reverse(self):
        """Auto-generated inverse static rows should also be removed."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.92"),
                rate_type=RateType.STATIC,
            )
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.08695652173913"),
                rate_type=RateType.STATIC,
            )
            replace_static_to_dynamic_monthly_rates("USD", "EUR", self.month_start, self.month_end)

            self.assertFalse(
                MonthlyExchangeRate.objects.filter(effective_date=self.month_start, rate_type=RateType.STATIC).exists()
            )

    def test_preserves_inverse_when_explicit_reverse_exists(self):
        """Inverse static rows should be preserved when a separate StaticExchangeRate defines the reverse."""
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.create(
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.10"),
                start_date=self.month_start,
                end_date=self.month_end,
            )
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.10"),
                rate_type=RateType.STATIC,
            )
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.92"),
                rate_type=RateType.STATIC,
            )
            replace_static_to_dynamic_monthly_rates("USD", "EUR", self.month_start, self.month_end)

            self.assertTrue(
                MonthlyExchangeRate.objects.filter(
                    effective_date=self.month_start,
                    base_currency="EUR",
                    target_currency="USD",
                    rate_type=RateType.STATIC,
                ).exists()
            )

    def test_no_backfill_when_no_exchange_dictionary(self):
        """No backfill should happen when ExchangeRateDictionary is empty."""
        ExchangeRateDictionary.objects.all().delete()

        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.92"),
                rate_type=RateType.STATIC,
            )
            replace_static_to_dynamic_monthly_rates("USD", "EUR", self.month_start, self.month_end)

            self.assertFalse(MonthlyExchangeRate.objects.filter(base_currency="USD", target_currency="EUR").exists())


class RemoveMonthlyRatesTest(MasuTestCase):
    """Tests for remove_monthly_rates."""

    def setUp(self):
        super().setUp()
        self.month_start = self.dh.this_month_start.date()
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.all().delete()

    def test_removes_both_static_and_dynamic_rows(self):
        """Both static and dynamic rows involving the currency should be removed."""
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.87"),
                rate_type=RateType.DYNAMIC,
            )
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_start,
                base_currency="EUR",
                target_currency="USD",
                exchange_rate=Decimal("1.15"),
                rate_type=RateType.STATIC,
            )
            deleted = remove_monthly_rates("USD")
            self.assertEqual(deleted, 2)
            self.assertFalse(
                MonthlyExchangeRate.objects.filter(effective_date=self.month_start)
                .filter(Q(base_currency="USD") | Q(target_currency="USD"))
                .exists()
            )


class PopulateDynamicMonthlyRatesBackfillTest(MasuTestCase):
    """Tests for retention-window backfill (Celery-only via backfill_past_months=True)."""

    def setUp(self):
        super().setUp()
        self.month_start = self.dh.this_month_start.date()
        # Retention months 1..6 with current = 6
        self.month_1 = (self.month_start - relativedelta(months=5)).replace(day=1)
        self.month_2 = (self.month_start - relativedelta(months=4)).replace(day=1)
        self.month_3 = (self.month_start - relativedelta(months=3)).replace(day=1)
        self.month_4 = (self.month_start - relativedelta(months=2)).replace(day=1)
        self.month_5 = (self.month_start - relativedelta(months=1)).replace(day=1)
        ExchangeRateDictionary.objects.all().delete()
        ExchangeRateDictionary.objects.create(
            currency_exchange_dictionary={"USD": {"EUR": "0.87", "USD": "1.0"}, "EUR": {"USD": "1.15", "EUR": "1.0"}}
        )
        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.all().delete()
            EnabledCurrency.objects.all().delete()
            EnabledCurrency.objects.create(currency_code="USD")
            EnabledCurrency.objects.create(currency_code="EUR")

    @patch("cost_models.monthly_exchange_rate_utils._backfill_missing_past_months")
    def test_default_does_not_backfill_past_months(self, mock_backfill):
        """Currency enable and other callers leave past months untouched."""
        with tenant_context(self.tenant):
            populate_dynamic_monthly_rates()
            self.assertTrue(
                MonthlyExchangeRate.objects.filter(
                    effective_date=self.month_start, base_currency="USD", target_currency="EUR"
                ).exists()
            )
            self.assertFalse(MonthlyExchangeRate.objects.filter(effective_date=self.month_5).exists())
            mock_backfill.assert_not_called()

    @patch("cost_models.monthly_exchange_rate_utils.materialized_view_month_start")
    def test_backfill_uses_next_later_existing_rate(self, mock_retention_start):
        """Gaps use the next later MER rate: 1<-2, 3<-4, 5<-current."""
        mock_retention_start.return_value = self.month_1

        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_2,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.20"),
                rate_type=RateType.DYNAMIC,
            )
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_4,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.40"),
                rate_type=RateType.STATIC,
            )

            populate_dynamic_monthly_rates(backfill_past_months=True)

            self.assertEqual(
                MonthlyExchangeRate.objects.get(
                    effective_date=self.month_1, base_currency="USD", target_currency="EUR"
                ).exchange_rate,
                Decimal("0.20"),
            )
            self.assertEqual(
                MonthlyExchangeRate.objects.get(
                    effective_date=self.month_3, base_currency="USD", target_currency="EUR"
                ).exchange_rate,
                Decimal("0.40"),
            )
            self.assertEqual(
                MonthlyExchangeRate.objects.get(
                    effective_date=self.month_5, base_currency="USD", target_currency="EUR"
                ).exchange_rate,
                Decimal("0.87"),
            )
            # Existing rows preserved
            self.assertEqual(
                MonthlyExchangeRate.objects.get(
                    effective_date=self.month_2, base_currency="USD", target_currency="EUR"
                ).exchange_rate,
                Decimal("0.20"),
            )
            self.assertEqual(
                MonthlyExchangeRate.objects.get(
                    effective_date=self.month_4, base_currency="USD", target_currency="EUR"
                ).rate_type,
                RateType.STATIC,
            )
            self.assertEqual(
                MonthlyExchangeRate.objects.get(
                    effective_date=self.month_start, base_currency="USD", target_currency="EUR"
                ).exchange_rate,
                Decimal("0.87"),
            )

    @patch("cost_models.monthly_exchange_rate_utils.materialized_view_month_start")
    def test_backfill_starts_from_month_before_latest_available(self, mock_retention_start):
        """Walk starts at latest_month-1; months after the latest available are not filled."""
        mock_retention_start.return_value = self.month_1

        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_2,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.20"),
                rate_type=RateType.DYNAMIC,
            )
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_4,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.40"),
                rate_type=RateType.DYNAMIC,
            )

            _backfill_missing_past_months({("USD", "EUR")}, self.month_start)

            # Latest available is month 4, so walk starts at month 3; month 5 stays empty.
            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    effective_date=self.month_5, base_currency="USD", target_currency="EUR"
                ).exists()
            )
            self.assertEqual(
                MonthlyExchangeRate.objects.get(
                    effective_date=self.month_3, base_currency="USD", target_currency="EUR"
                ).exchange_rate,
                Decimal("0.40"),
            )
            self.assertEqual(
                MonthlyExchangeRate.objects.get(
                    effective_date=self.month_1, base_currency="USD", target_currency="EUR"
                ).exchange_rate,
                Decimal("0.20"),
            )
            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    effective_date=self.month_start, base_currency="USD", target_currency="EUR"
                ).exists()
            )

    @patch("cost_models.monthly_exchange_rate_utils.materialized_view_month_start")
    def test_backfill_fills_all_gaps_before_latest_with_same_rate(self, mock_retention_start):
        """If only month 4 exists, months 3 and 2 (and 1) are filled with month 4's rate."""
        mock_retention_start.return_value = self.month_1

        with tenant_context(self.tenant):
            MonthlyExchangeRate.objects.create(
                effective_date=self.month_4,
                base_currency="USD",
                target_currency="EUR",
                exchange_rate=Decimal("0.40"),
                rate_type=RateType.DYNAMIC,
            )

            _backfill_missing_past_months({("USD", "EUR")}, self.month_start)

            for month in (self.month_1, self.month_2, self.month_3):
                self.assertEqual(
                    MonthlyExchangeRate.objects.get(
                        effective_date=month, base_currency="USD", target_currency="EUR"
                    ).exchange_rate,
                    Decimal("0.40"),
                )
            self.assertFalse(
                MonthlyExchangeRate.objects.filter(
                    effective_date=self.month_5, base_currency="USD", target_currency="EUR"
                ).exists()
            )
