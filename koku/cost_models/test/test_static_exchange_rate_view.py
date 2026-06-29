#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for StaticExchangeRate CRUD views."""
import uuid
from datetime import date

from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from cost_models.models import StaticExchangeRate


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
        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": today.replace(day=28).isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data
        self.assertIn("uuid", data)
        self.assertEqual(data["name"], "USD-EUR")
        self.assertEqual(data["base_currency"], "USD")
        self.assertEqual(data["target_currency"], "EUR")
        self.assertEqual(data["exchange_rate"], "0.920000000000000")
        self.assertEqual(data["start_date"], today.replace(day=1).isoformat())
        self.assertEqual(data["end_date"], today.replace(day=28).isoformat())
        self.assertIn("created_timestamp", data)
        self.assertIn("updated_timestamp", data)

        with tenant_context(self.tenant):
            self.assertEqual(StaticExchangeRate.objects.count(), 1)
            db_rate = StaticExchangeRate.objects.get(uuid=data["uuid"])
            self.assertEqual(db_rate.base_currency, "USD")
            self.assertEqual(db_rate.target_currency, "EUR")
            self.assertEqual(str(db_rate.exchange_rate), "0.920000000000000")
            self.assertEqual(db_rate.start_date, today.replace(day=1))
            self.assertEqual(db_rate.end_date, today.replace(day=28))

    def test_create_same_currency_pair_rejected(self):
        today = timezone.now().date()
        payload = {
            "base_currency": "USD",
            "target_currency": "USD",
            "exchange_rate": 1.0,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": today.replace(day=28).isoformat(),
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
            "end_date": today.replace(day=28).isoformat(),
        }
        response = self.client.post(self.url, payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_end_before_start_rejected(self):
        today = timezone.now().date()
        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.92,
            "start_date": today.replace(day=28).isoformat(),
            "end_date": today.replace(day=1).isoformat(),
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
        with tenant_context(self.tenant):
            StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=today.replace(day=1),
                end_date=today.replace(day=28),
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.95,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": today.replace(day=28).isoformat(),
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
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=today.replace(day=1),
                end_date=today.replace(day=28),
            )

        payload = {
            "base_currency": "USD",
            "target_currency": "EUR",
            "exchange_rate": 0.95,
            "start_date": today.replace(day=1).isoformat(),
            "end_date": today.replace(day=28).isoformat(),
        }
        response = self.client.put(self._url(rate.uuid), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["exchange_rate"], "0.950000000000000")

    def test_update_past_month_rejected(self):
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

    def test_delete_rate(self):
        today = timezone.now().date()
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=today.replace(day=1),
                end_date=today.replace(day=28),
            )

        response = self.client.delete(self._url(rate.uuid), **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        with tenant_context(self.tenant):
            self.assertEqual(StaticExchangeRate.objects.count(), 0)

    def test_delete_past_month_rejected(self):
        with tenant_context(self.tenant):
            rate = StaticExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                exchange_rate="0.920000000000000",
                start_date=date(2020, 1, 1),
                end_date=date(2020, 1, 31),
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
            "end_date": today.replace(day=28).isoformat(),
        }
        response = self.client.put(self._url(uuid.uuid4()), payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
