#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for exchange rate annotation builders and feature-flag gating."""
from datetime import date
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db.models import Case
from django.db.models import Q
from django.db.models import Subquery
from django.test import TestCase
from django_tenants.utils import schema_context
from django_tenants.utils import tenant_context

from api.currency.exceptions import ExchangeRateNotFound
from api.currency.utils import build_monthly_rate_annotation
from api.currency.utils import get_monthly_exchange_rate_map
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

    def test_rate_map_returns_rates_and_identity(self):
        """get_monthly_exchange_rate_map returns DB rates and target-currency identity rates."""
        with schema_context(self.schema):
            MonthlyExchangeRate.objects.create(
                effective_date=date(2026, 1, 1),
                base_currency="GBP",
                target_currency="EUR",
                exchange_rate=Decimal("1.17"),
                rate_type="static",
            )
            rate_map = get_monthly_exchange_rate_map({"GBP", "EUR"}, "EUR", date(2026, 1, 1), date(2026, 1, 31))

        self.assertEqual(rate_map["GBP"][date(2026, 1, 1)], Decimal("1.17"))
        self.assertEqual(rate_map["EUR"][date(2026, 1, 1)], Decimal("1"))


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
    def test_ocp_flag_on_applies_monthly_rates_by_source_and_raw_currency(self, _):
        """Flag ON applies the correct monthly cost-model and infrastructure rates."""
        handler = self._make_ocp_handler()
        source_uuid = self.ocp_provider.uuid
        september_id = uuid4()
        october_id = uuid4()
        with tenant_context(handler.tenant):
            handler.query_table.objects.bulk_create(
                [
                    handler.query_table(
                        id=september_id,
                        cluster_id="exchange-rate-test",
                        usage_start=date(2026, 9, 15),
                        usage_end=date(2026, 9, 16),
                        source_uuid_id=source_uuid,
                        raw_currency="USD",
                    ),
                    handler.query_table(
                        id=october_id,
                        cluster_id="exchange-rate-test",
                        usage_start=date(2026, 10, 15),
                        usage_end=date(2026, 10, 16),
                        source_uuid_id=source_uuid,
                        raw_currency="USD",
                    ),
                ]
            )

        handler.__dict__["request_source_to_currency_map"] = {source_uuid: "GBP"}
        handler.__dict__["raw_currencies_for_conversion"] = {"USD"}
        handler.__dict__["monthly_exchange_rate_map"] = {
            "GBP": {date(2026, 9, 1): Decimal("1.10"), date(2026, 10, 1): Decimal("1.20")},
            "USD": {date(2026, 9, 1): Decimal("0.90"), date(2026, 10, 1): Decimal("0.80")},
        }

        with tenant_context(handler.tenant):
            rows = list(
                handler.query_table.objects.filter(id__in=[september_id, october_id])
                .annotate(**handler.exchange_rate_annotation_dict)
                .order_by("usage_start")
                .values_list("exchange_rate", "infra_exchange_rate")
            )

        self.assertEqual(rows, [(Decimal("1.10"), Decimal("0.90")), (Decimal("1.20"), Decimal("0.80"))])

    def test_ocp_conversion_inputs_follow_report_filters_and_exclusions(self):
        """Currency discovery uses the same filtered and access-scoped rows as the report."""
        handler = self._make_ocp_handler()
        included_id = uuid4()
        excluded_id = uuid4()
        with tenant_context(handler.tenant):
            handler.query_table.objects.bulk_create(
                [
                    handler.query_table(
                        id=included_id,
                        cluster_id="included-cluster",
                        usage_start=handler.start_datetime.date(),
                        usage_end=handler.start_datetime.date(),
                        source_uuid_id=self.ocp_provider.uuid,
                        raw_currency="EUR",
                    ),
                    handler.query_table(
                        id=excluded_id,
                        cluster_id="excluded-cluster",
                        usage_start=handler.start_datetime.date(),
                        usage_end=handler.start_datetime.date(),
                        source_uuid_id=self.ocp_on_aws_ocp_provider.uuid,
                        raw_currency="CAD",
                    ),
                ]
            )
            handler.query_filter = Q(id__in=[included_id, excluded_id])
            handler.query_exclusions = Q(id=excluded_id)

            self.assertEqual(handler.source_uuids_for_conversion, {self.ocp_provider.uuid})
            self.assertEqual(handler.raw_currencies_for_conversion, {"EUR"})

    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True)
    def test_ocp_delta_annotations_include_previous_period_rates(self, _):
        """Previous-period delta rows use monthly rates instead of the identity default."""
        handler = self._make_ocp_handler()
        handler._delta = "cost_total"
        handler.currency = "EUR"
        handler.start_datetime = datetime(2026, 10, 1)
        handler.end_datetime = datetime(2026, 10, 31)
        source_uuid = self.ocp_provider.uuid
        previous_id = uuid4()
        current_id = uuid4()
        with schema_context(self.schema):
            for month_start, rate in [(date(2026, 9, 1), Decimal("0.70")), (date(2026, 10, 1), Decimal("0.80"))]:
                MonthlyExchangeRate.objects.update_or_create(
                    effective_date=month_start,
                    base_currency="USD",
                    target_currency="EUR",
                    defaults={"exchange_rate": rate, "rate_type": "static"},
                )

        with tenant_context(handler.tenant):
            handler.query_table.objects.bulk_create(
                [
                    handler.query_table(
                        id=previous_id,
                        cluster_id="delta-exchange-rate-test",
                        usage_start=date(2026, 9, 15),
                        usage_end=date(2026, 9, 16),
                        source_uuid_id=source_uuid,
                        raw_currency="USD",
                    ),
                    handler.query_table(
                        id=current_id,
                        cluster_id="delta-exchange-rate-test",
                        usage_start=date(2026, 10, 15),
                        usage_end=date(2026, 10, 16),
                        source_uuid_id=source_uuid,
                        raw_currency="USD",
                    ),
                ]
            )

            handler.query_filter = Q(id=current_id)
            handler.__dict__["request_source_to_currency_map"] = {source_uuid: "USD"}

            previous_rate = (
                handler.query_table.objects.filter(id=previous_id)
                .annotate(**handler.exchange_rate_annotation_dict)
                .values_list("exchange_rate", flat=True)
                .get()
            )

        self.assertEqual(previous_rate, Decimal("0.70"))

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
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG, dev_fallback=True)

    @patch("api.query_handler.is_feature_flag_enabled_by_schema", return_value=False)
    def test_base_handler_flag_off_uses_case(self, mock_flag):
        """Flag OFF → base QueryHandler path (AWS) returns a Case annotation."""
        handler = self._make_aws_handler()
        with schema_context(self.schema):
            ann = handler.exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate"})
        self.assertIsInstance(ann["exchange_rate"], Case)
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG, dev_fallback=True)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.queries.validate_exchange_rate_coverage")
    def test_initialize_response_output(self, mock_validate, mock_flag):
        """_initialize_response_output includes currency and calls validation (flag ON)."""
        handler = self._make_ocp_handler()
        output = handler._initialize_response_output(handler.parameters)
        self.assertIn("currency", output)
        mock_validate.assert_called_once()
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG, dev_fallback=True)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=False)
    @patch("api.report.queries.validate_exchange_rate_coverage")
    def test_initialize_response_output_skips_validation_when_flag_off(self, mock_validate, mock_flag):
        """_initialize_response_output skips validate_exchange_rate_coverage when flag is off."""
        handler = self._make_ocp_handler()
        output = handler._initialize_response_output(handler.parameters)
        self.assertIn("currency", output)
        mock_validate.assert_not_called()
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG, dev_fallback=True)

    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=False)
    def test_get_base_currencies_returns_set(self, _):
        """_get_base_currencies_for_conversion returns a set excluding None."""
        handler = self._make_ocp_handler()
        with tenant_context(handler.tenant):
            currencies = handler._get_base_currencies_for_conversion()
        self.assertIsInstance(currencies, set)
        self.assertNotIn(None, currencies)
