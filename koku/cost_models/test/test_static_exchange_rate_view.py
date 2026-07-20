#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for StaticExchangeRate CRUD views."""
import calendar
import uuid
from datetime import date
from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import StaticExchangeRate
from cost_models.static_exchange_rate_serializer import TrailingZeroStrippingDecimalField


def _month_end(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


class TrailingZeroStrippingDecimalFieldTest(SimpleTestCase):
    """Unit tests for API decimal representation of exchange rates."""

    def test_strips_trailing_zeros_preserves_precision(self):
        field = TrailingZeroStrippingDecimalField(max_digits=33, decimal_places=15)
        cases = (
            (None, None),
            ("1.500000000000000", "1.5"),
            (Decimal("1.500000000000000"), "1.5"),
            (Decimal("0.920000000000000"), "0.92"),
            (Decimal("1.234567890123456"), "1.234567890123456"),
            (Decimal("100.000000000000000"), "100"),
            (Decimal("0.000000000000001"), "0.000000000000001"),
            # Parent DecimalField quantizes to decimal_places=15 before we strip zeros
            (Decimal("1." + ("2" * 31)), "1.222222222222222"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(field.to_representation(value), expected)


class StaticExchangeRateListViewTest(IamTestCase):
    """Tests for GET/POST settings/currency/static-rates/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = reverse("static-exchange-rate-list")
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.all().delete()

    def test_create_rate(self):
        today = timezone.now().date()
        month_start = today.replace(day=1)
        month_end = _month_end(today)
        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": month_start.isoformat(),
            "end_date": month_end.isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data
        self.assertIn("uuid", data)
        self.assertEqual(data["name"], "USD-EUR")
        self.assertEqual(data["base_currency"], "USD")
        self.assertEqual(data["target_currency"], "EUR")
        self.assertEqual(data["exchange_rate"], "0.92")
        self.assertEqual(data["start_date"], month_start.isoformat())
        self.assertEqual(data["end_date"], month_end.isoformat())
        self.assertIn("created_timestamp", data)
        self.assertIn("updated_timestamp", data)

    def test_create_same_currency_pair_rejected(self):
        today = timezone.now().date()
        payload = {
            "base_currency": "USD",
            "target_currency": "USD",
            "exchange_rate": 1.0,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": _month_end(today).isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_invalid_currency_rejected(self):
        today = timezone.now().date()
        payload = {
            "base_currency": "ZZZ",
            "target_currency": "EUR",
            "exchange_rate": 1.0,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": _month_end(today).isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_end_before_start_rejected(self):
        today = timezone.now().date()
        month_end = _month_end(today)
        next_month_start = _month_end(today) + timedelta(days=1)
        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": next_month_start.isoformat(),
            "end_date": month_end.isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_past_month_rejected(self):
        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_overlapping_range_rejected(self):
        today = timezone.now().date()
        month_start = today.replace(day=1)
        month_end = _month_end(today)
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=month_start,
                end_date=month_end,
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.95,
            "start_date": month_start.isoformat(),
            "end_date": month_end.isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_start_not_first_of_month_rejected(self):
        today = timezone.now().date()
        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": today.replace(day=15).isoformat(),
            "end_date": _month_end(today).isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_end_not_last_of_month_rejected(self):
        today = timezone.now().date()
        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": today.replace(day=15).isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StaticExchangeRateDetailViewTest(IamTestCase):
    """Tests for PUT/DELETE settings/currency/static-rates/<uuid>/."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.all().delete()

    def _url(self, uuid):
        return reverse("static-exchange-rate-detail", kwargs={"uuid": uuid})

    def test_update_rate(self):
        today = timezone.now().date()
        month_start = today.replace(day=1)
        month_end = _month_end(today)
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=month_start,
                end_date=month_end,
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.95,
            "start_date": month_start.isoformat(),
            "end_date": month_end.isoformat(),
        }
        response = self.client.put(self._url(rate.uuid), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["exchange_rate"], "0.95")

    def test_update_fully_finalized_rejected(self):
        """A rate whose end_date is entirely in the past cannot be edited."""
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=date(2020, 1, 1),
                end_date=date(2020, 1, 31),
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.95,
            "start_date": "2020-01-01",
            "end_date": "2020-01-31",
        }
        response = self.client.put(self._url(rate.uuid), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_rate_spanning_past_and_current(self):
        """A rate with start_date in the past but end_date in current/future months is editable."""
        today = timezone.now().date()
        past_start = date(2020, 1, 1)
        future_end = _month_end(today)
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=past_start,
                end_date=future_end,
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.95,
            "start_date": past_start.isoformat(),
            "end_date": future_end.isoformat(),
        }
        response = self.client.put(self._url(rate.uuid), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["exchange_rate"], "0.95")

    def test_update_shrink_end_date_to_past(self):
        """User can shrink end_date to close out a rate"""
        today = timezone.now().date()
        current_month_start = today.replace(day=1)
        past_start = date(2020, 1, 1)
        prev_month_end = _month_end(current_month_start - timedelta(days=1))
        future_end = _month_end(today)
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=past_start,
                end_date=future_end,
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": past_start.isoformat(),
            "end_date": prev_month_end.isoformat(),
        }
        response = self.client.put(self._url(rate.uuid), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["end_date"], prev_month_end.isoformat())

    def test_update_shrink_end_date_beyond_prev_month_rejected(self):
        """Cannot shrink end_date further back than the previous month."""
        today = timezone.now().date()
        past_start = date(2020, 1, 1)
        two_months_ago_end = _month_end(today.replace(day=1) - timedelta(days=60))
        future_end = _month_end(today)
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=past_start,
                end_date=future_end,
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": past_start.isoformat(),
            "end_date": two_months_ago_end.isoformat(),
        }
        response = self.client.put(self._url(rate.uuid), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_change_start_date_on_started_rate_rejected(self):
        """Changing start_date on a rate that has already started is not allowed."""
        today = timezone.now().date()
        past_start = date(2020, 1, 1)
        future_end = _month_end(today)
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=past_start,
                end_date=future_end,
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": future_end.isoformat(),
        }
        response = self.client.put(self._url(rate.uuid), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_change_start_date_on_future_rate_allowed(self):
        """Changing start_date on a rate that hasn't started yet is allowed."""
        today = timezone.now().date()
        next_month_start = _month_end(today) + timedelta(days=1)
        next_month_end = _month_end(next_month_start)
        month_after_start = next_month_end + timedelta(days=1)
        month_after_end = _month_end(month_after_start)
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=next_month_start,
                end_date=next_month_end,
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": month_after_start.isoformat(),
            "end_date": month_after_end.isoformat(),
        }
        response = self.client.put(self._url(rate.uuid), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["start_date"], month_after_start.isoformat())

    def test_delete_rate(self):
        today = timezone.now().date()
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=today.replace(day=1),
                end_date=_month_end(today),
            )

        response = self.client.delete(self._url(rate.uuid), **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        with tenant_context(self.tenant):
            self.assertEqual(StaticExchangeRate.objects.count(), 0)

    def test_delete_rate_with_finalized_months(self):
        """A rate with start_date in the past cannot be deleted."""
        today = timezone.now().date()
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=date(2020, 1, 1),
                end_date=_month_end(today),
            )

        response = self.client.delete(self._url(rate.uuid), **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_nonexistent_returns_404(self):
        response = self.client.delete(self._url(uuid.uuid4()), **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_nonexistent_returns_404(self):
        today = timezone.now().date()
        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.95,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": _month_end(today).isoformat(),
        }
        response = self.client.put(self._url(uuid.uuid4()), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
