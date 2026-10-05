#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for exchange rate annotation builders and feature-flag gating."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db.models import Case
from django.db.models import Subquery
from django.test import TestCase
from django_tenants.utils import schema_context
from django_tenants.utils import tenant_context

from api.currency.exceptions import ExchangeRateNotFound
from api.currency.utils import build_monthly_rate_annotation
from api.currency.utils import validate_exchange_rate_coverage
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.view import AWSCostView
from api.report.ocp.view import OCPCostView
from cost_models.models import MonthlyExchangeRate
from masu.processor import CONSTANT_CURRENCY_FLAG
from masu.test import MasuTestCase


class AnnotationBuilderTest(TestCase):
    """Test that build_monthly_rate_annotation returns a Subquery expression."""

    def test_returns_subquery(self):
        from django.db.models import OuterRef
        from django.db.models import Subquery

        result = build_monthly_rate_annotation(OuterRef("raw_currency"), "EUR")
        self.assertIsInstance(result, Subquery)


class ValidateExchangeRateCoverageTest(MasuTestCase):
    """Tests for validate_exchange_rate_coverage()."""

    def test_raises_when_currency_completely_missing(self):
        """Raises ExchangeRateNotFound when no MER rows exist for a base currency."""
        with (
            schema_context(self.schema),
            self.assertRaises(ExchangeRateNotFound),
        ):
            validate_exchange_rate_coverage({"GBP"}, "EUR", date(2026, 1, 1), date(2026, 1, 31))

    def test_raises_when_monthly_gap_exists(self):
        """Raises ExchangeRateNotFound when a month has no rate for a covered currency."""
        with schema_context(self.schema):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 1, 1),
                base_currency="GBP",
                target_currency="EUR",
                exchange_rate=Decimal("1.17"),
                rate_type="static",
            )
            with self.assertRaises(ExchangeRateNotFound):
                validate_exchange_rate_coverage({"GBP"}, "EUR", date(2026, 1, 1), date(2026, 2, 1))

    def test_passes_when_all_months_covered(self):
        """No exception when every month in the range has an MER row."""
        with schema_context(self.schema):
            for month in [date(2026, 1, 1), date(2026, 2, 1)]:
                MonthlyExchangeRate.objects.create(
                    effective_date=month,
                    base_currency="GBP",
                    target_currency="EUR",
                    exchange_rate=Decimal("1.17"),
                    rate_type="static",
                )
            validate_exchange_rate_coverage({"GBP"}, "EUR", date(2026, 1, 1), date(2026, 2, 1))


class QueryHandlerFeatureFlagTest(MasuTestCase):
    """Test that the feature flag gates exchange-rate behaviour in query handlers."""

    OCP_PATH = "/api/cost-management/v1/reports/openshift/costs/"
    AWS_PATH = "/api/cost-management/v1/reports/aws/costs/"

    def _make_ocp_handler(self):
        from api.report.ocp.query_handler import OCPReportQueryHandler

        return OCPReportQueryHandler(self.mocked_query_params("?", OCPCostView, path=self.OCP_PATH))

    def _make_aws_handler(self):
        return AWSReportQueryHandler(self.mocked_query_params("?", AWSCostView, path=self.AWS_PATH))

    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True)
    def test_flag_on_uses_subquery_annotations(self, _):
        """Flag ON → OCP handler returns Subquery-based annotations (both keys present)."""
        ann = self._make_ocp_handler().exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate", "infra_exchange_rate"})

    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=False)
    def test_flag_off_uses_dict_annotations(self, _):
        """Flag OFF → OCP handler returns Case/When annotations (both keys present)."""
        with schema_context(self.schema):
            ann = self._make_ocp_handler().exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate", "infra_exchange_rate"})

    @patch("api.query_handler.is_feature_flag_enabled_by_schema", return_value=True)
    def test_base_handler_flag_on_uses_subquery(self, mock_flag):
        """Flag ON → base QueryHandler path (AWS) returns a Subquery annotation."""
        handler = self._make_aws_handler()
        ann = handler.exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate"})
        self.assertIsInstance(ann["exchange_rate"], Subquery)
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG)

    @patch("api.query_handler.is_feature_flag_enabled_by_schema", return_value=False)
    def test_base_handler_flag_off_uses_case(self, mock_flag):
        """Flag OFF → base QueryHandler path (AWS) returns a Case annotation."""
        handler = self._make_aws_handler()
        with schema_context(self.schema):
            ann = handler.exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate"})
        self.assertIsInstance(ann["exchange_rate"], Case)
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.queries.validate_exchange_rate_coverage")
    def test_initialize_response_output(self, mock_validate, mock_flag):
        """_initialize_response_output includes currency and calls validation (flag ON)."""
        handler = self._make_ocp_handler()
        output = handler._initialize_response_output(handler.parameters)
        self.assertIn("currency", output)
        mock_validate.assert_called_once()
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=False)
    @patch("api.report.queries.validate_exchange_rate_coverage")
    def test_initialize_response_output_skips_validation_when_flag_off(self, mock_validate, mock_flag):
        """_initialize_response_output skips validate_exchange_rate_coverage when flag is off."""
        handler = self._make_ocp_handler()
        output = handler._initialize_response_output(handler.parameters)
        self.assertIn("currency", output)
        mock_validate.assert_not_called()
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG)

    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=False)
    def test_get_base_currencies_returns_set(self, _):
        """_get_base_currencies_for_conversion returns a set excluding None."""
        handler = self._make_ocp_handler()
        with tenant_context(handler.tenant):
            currencies = handler._get_base_currencies_for_conversion()
        self.assertIsInstance(currencies, set)
        self.assertNotIn(None, currencies)
