#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for exchange rate annotation builders and feature-flag gating."""
from unittest.mock import patch

from django.test import TestCase
from django_tenants.utils import schema_context

from api.currency.exceptions import ExchangeRateNotFound
from api.currency.utils import build_monthly_rate_annotation
from api.report.ocp.view import OCPCostView
from masu.test import MasuTestCase


class ExchangeRateNotFoundTest(TestCase):
    """Test error message formatting for ExchangeRateNotFound."""

    @patch("api.currency.exceptions.settings")
    def test_message_with_currency_url(self, mock_settings):
        mock_settings.CURRENCY_URL = "https://example.com"
        exc = ExchangeRateNotFound(["USD", "GBP"], "EUR", "2026-01-01", "2026-03-01")
        msg = exc.detail["currency"]
        self.assertIn("USD -> EUR", msg)
        self.assertIn("GBP -> EUR", msg)
        self.assertNotIn("dynamic exchange rates", msg)

    @patch("api.currency.exceptions.settings")
    def test_message_without_currency_url(self, mock_settings):
        mock_settings.CURRENCY_URL = ""
        exc = ExchangeRateNotFound(["USD"], "EUR", "2026-01-01", "2026-03-01")
        msg = exc.detail["currency"]
        self.assertIn("dynamic exchange rates", msg)


class AnnotationBuilderTest(TestCase):
    """Test that build_monthly_rate_annotation returns a Subquery expression."""

    def test_returns_subquery(self):
        from django.db.models import OuterRef
        from django.db.models import Subquery

        result = build_monthly_rate_annotation(OuterRef("raw_currency"), "EUR")
        self.assertIsInstance(result, Subquery)


class QueryHandlerFeatureFlagTest(MasuTestCase):
    """Test that the feature flag gates exchange-rate behaviour in query handlers."""

    OCP_PATH = "/api/cost-management/v1/reports/openshift/costs/"

    def _make_handler(self):
        from api.report.ocp.query_handler import OCPReportQueryHandler

        return OCPReportQueryHandler(self.mocked_query_params("?", OCPCostView, path=self.OCP_PATH))

    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True)
    def test_flag_on_uses_subquery_annotations(self, _):
        """Flag ON → OCP handler returns Subquery-based annotations (both keys present)."""
        ann = self._make_handler().exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate", "infra_exchange_rate"})

    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=False)
    def test_flag_off_uses_dict_annotations(self, _):
        """Flag OFF → OCP handler returns Case/When annotations (both keys present)."""
        with schema_context(self.schema):
            ann = self._make_handler().exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate", "infra_exchange_rate"})

    def test_response_output_includes_currency(self):
        """_initialize_response_output always includes currency."""
        handler = self._make_handler()
        output = handler._initialize_response_output(handler.parameters)
        self.assertIn("currency", output)
