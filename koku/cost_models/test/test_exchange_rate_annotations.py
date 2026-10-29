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
from api.report.all.openshift.query_handler import OCPAllReportQueryHandler
from api.report.all.openshift.view import OCPAllCostView
from api.report.aws.openshift.query_handler import OCPAWSReportQueryHandler
from api.report.aws.openshift.view import OCPAWSCostView
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.view import AWSCostView
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.openshift.view import OCPAzureCostView
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.azure.view import AzureCostView
from api.report.gcp.openshift.query_handler import OCPGCPReportQueryHandler
from api.report.gcp.openshift.view import OCPGCPCostView
from api.report.gcp.query_handler import GCPReportQueryHandler
from api.report.gcp.view import GCPCostView
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


class GetMonthlyExchangeRateMapTest(MasuTestCase):
    """Tests for get_monthly_exchange_rate_map()."""

    def test_raises_when_currency_completely_missing(self):
        """Raises ExchangeRateNotFound when no MER rows exist for a base currency."""
        with (
            schema_context(self.schema),
            self.assertRaises(ExchangeRateNotFound),
        ):
            get_monthly_exchange_rate_map({"GBP"}, "EUR", date(2026, 1, 1), date(2026, 1, 31))

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
                get_monthly_exchange_rate_map({"GBP"}, "EUR", date(2026, 1, 1), date(2026, 2, 1))

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
            get_monthly_exchange_rate_map({"GBP"}, "EUR", date(2026, 1, 1), date(2026, 2, 1))

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

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    def test_base_handler_flag_on_uses_monthly_case(self, mock_flag):
        """Flag ON → base report handler path (AWS) returns a bounded Case, not a Subquery."""
        handler = self._make_aws_handler()
        handler.__dict__["raw_currencies_for_conversion"] = {"USD"}
        handler.__dict__["monthly_exchange_rate_map"] = {"USD": {date(2026, 10, 1): Decimal("0.80")}}
        ann = handler.exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate"})
        self.assertIsInstance(ann["exchange_rate"], Case)
        self.assertNotIsInstance(ann["exchange_rate"], Subquery)
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG, dev_fallback=True)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=False)
    def test_base_handler_flag_off_uses_case(self, mock_flag):
        """Flag OFF → base QueryHandler path (AWS) returns a Case annotation."""
        handler = self._make_aws_handler()
        with schema_context(self.schema):
            ann = handler.exchange_rate_annotation_dict
        self.assertEqual(set(ann.keys()), {"exchange_rate"})
        self.assertIsInstance(ann["exchange_rate"], Case)
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG, dev_fallback=True)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.queries.get_monthly_exchange_rate_map")
    def test_initialize_response_output(self, mock_get_monthly_exchange_rate_map, mock_flag):
        """_initialize_response_output includes currency and calls validation (flag ON)."""
        handler = self._make_ocp_handler()
        output = handler._initialize_response_output(handler.parameters)
        self.assertIn("currency", output)
        mock_get_monthly_exchange_rate_map.assert_called_once()
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG, dev_fallback=True)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=False)
    @patch("api.report.queries.get_monthly_exchange_rate_map")
    def test_initialize_response_output_skips_validation_when_flag_off(
        self, mock_get_monthly_exchange_rate_map, mock_flag
    ):
        """_initialize_response_output skips get_monthly_exchange_rate_map when flag is off."""
        handler = self._make_ocp_handler()
        output = handler._initialize_response_output(handler.parameters)
        self.assertIn("currency", output)
        mock_get_monthly_exchange_rate_map.assert_not_called()
        mock_flag.assert_called_with(handler.tenant.schema_name, CONSTANT_CURRENCY_FLAG, dev_fallback=True)

    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=False)
    def test_get_base_currencies_returns_set(self, _):
        """_get_base_currencies_for_conversion returns a set excluding None."""
        handler = self._make_ocp_handler()
        with tenant_context(handler.tenant):
            currencies = handler._get_base_currencies_for_conversion()
        self.assertIsInstance(currencies, set)
        self.assertNotIn(None, currencies)


class CloudReportExchangeRateTest(MasuTestCase):
    """Constant-currency conversion for the non-OCP report handlers."""

    AWS_PATH = "/api/cost-management/v1/reports/aws/costs/"

    def _make_aws_handler(self, query="?"):
        return AWSReportQueryHandler(self.mocked_query_params(query, AWSCostView, path=self.AWS_PATH))

    def _create_aws_rows(self, handler, rows):
        """Create AWS cost summary rows from (usage_start, currency_code) pairs and return their ids."""
        ids = [uuid4() for _ in rows]
        with tenant_context(handler.tenant):
            handler.query_table.objects.bulk_create(
                [
                    handler.query_table(
                        id=row_id,
                        usage_start=usage_start,
                        usage_end=usage_start,
                        source_uuid_id=self.aws_provider.uuid,
                        currency_code=currency,
                    )
                    for row_id, (usage_start, currency) in zip(ids, rows)
                ]
            )
        return ids

    def _create_rates(self, base_currency, target_currency, rates):
        with schema_context(self.schema):
            for month_start, rate in rates.items():
                MonthlyExchangeRate.objects.update_or_create(
                    effective_date=month_start,
                    base_currency=base_currency,
                    target_currency=target_currency,
                    defaults={"exchange_rate": rate, "rate_type": "static"},
                )

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    def test_cloud_handlers_flag_on_use_monthly_case(self, _):
        """Every non-OCP report handler builds the bounded Case instead of a per-row Subquery."""
        handlers = [
            (AWSReportQueryHandler, AWSCostView, "aws/costs/"),
            (AzureReportQueryHandler, AzureCostView, "azure/costs/"),
            (GCPReportQueryHandler, GCPCostView, "gcp/costs/"),
            (OCPAWSReportQueryHandler, OCPAWSCostView, "openshift/infrastructures/aws/costs/"),
            (OCPAzureReportQueryHandler, OCPAzureCostView, "openshift/infrastructures/azure/costs/"),
            (OCPGCPReportQueryHandler, OCPGCPCostView, "openshift/infrastructures/gcp/costs/"),
            (OCPAllReportQueryHandler, OCPAllCostView, "openshift/infrastructures/all/costs/"),
        ]
        rate_map = {"USD": {date(2026, 9, 1): Decimal("0.70"), date(2026, 10, 1): Decimal("0.80")}}
        for handler_class, view, path in handlers:
            with self.subTest(handler=handler_class.__name__):
                handler = handler_class(
                    self.mocked_query_params("?", view, path=f"/api/cost-management/v1/reports/{path}")
                )
                handler.__dict__["raw_currencies_for_conversion"] = {"USD"}
                handler.__dict__["monthly_exchange_rate_map"] = rate_map
                annotation = handler.exchange_rate_annotation_dict["exchange_rate"]
                self.assertIsInstance(annotation, Case)
                self.assertEqual(len(annotation.cases), 2)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    def test_aws_flag_on_applies_monthly_rates(self, _):
        """Each row gets the MonthlyExchangeRate for its own month."""
        handler = self._make_aws_handler()
        handler.currency = "EUR"
        handler.start_datetime = datetime(2026, 9, 1)
        handler.end_datetime = datetime(2026, 10, 31)
        self._create_rates("USD", "EUR", {date(2026, 9, 1): Decimal("0.70"), date(2026, 10, 1): Decimal("0.80")})
        ids = self._create_aws_rows(handler, [(date(2026, 9, 15), "USD"), (date(2026, 10, 15), "USD")])

        with tenant_context(handler.tenant):
            handler.query_filter = Q(id__in=ids)
            rates = list(
                handler.query_table.objects.filter(id__in=ids)
                .annotate(**handler.exchange_rate_annotation_dict)
                .order_by("usage_start")
                .values_list("exchange_rate", flat=True)
            )

        self.assertEqual(rates, [Decimal("0.70"), Decimal("0.80")])

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    def test_aws_delta_annotations_include_previous_period_rates(self, _):
        """Previous-period delta rows use monthly rates instead of the identity default."""
        handler = self._make_aws_handler()
        handler._delta = "cost_total"
        handler.currency = "EUR"
        handler.start_datetime = datetime(2026, 10, 1)
        handler.end_datetime = datetime(2026, 10, 31)
        self._create_rates("USD", "EUR", {date(2026, 9, 1): Decimal("0.70"), date(2026, 10, 1): Decimal("0.80")})
        previous_id, current_id = self._create_aws_rows(
            handler, [(date(2026, 9, 25), "USD"), (date(2026, 10, 15), "USD")]
        )

        with tenant_context(handler.tenant):
            handler.query_filter = Q(id=current_id)
            previous_rate = (
                handler.query_table.objects.filter(id=previous_id)
                .annotate(**handler.exchange_rate_annotation_dict)
                .values_list("exchange_rate", flat=True)
                .get()
            )

        self.assertEqual(previous_rate, Decimal("0.70"))

    def test_aws_conversion_inputs_follow_report_filters_and_exclusions(self):
        """Currency discovery uses the report's filters and exclusions, not the whole table."""
        handler = self._make_aws_handler()
        day = handler.start_datetime.date()
        included_id, excluded_id = self._create_aws_rows(handler, [(day, "EUR"), (day, "CAD")])

        with tenant_context(handler.tenant):
            handler.query_filter = Q(id__in=[included_id, excluded_id])
            handler.query_exclusions = Q(id=excluded_id)
            self.assertEqual(handler.raw_currencies_for_conversion, {"EUR"})
            self.assertEqual(handler._get_base_currencies_for_conversion(), {"EUR"})

    def test_aws_org_unit_conversion_inputs_ignore_per_sub_org_filter(self):
        """Org unit requests discover currencies across the date range, whatever query_filter is current."""
        handler = self._make_aws_handler("?group_by[org_unit_id]=R_001")
        self.assertTrue(handler._org_unit_requested)
        day = handler.start_datetime.date()
        first_org_id, _ = self._create_aws_rows(handler, [(day, "EUR"), (day, "CAD")])

        with tenant_context(handler.tenant):
            # execute_query() narrows query_filter per sub-org; conversion must still see every currency.
            handler.query_filter = Q(id=first_org_id)
            self.assertTrue({"EUR", "CAD"}.issubset(handler.raw_currencies_for_conversion))

    def test_aws_monthly_rate_map_raises_on_missing_month(self):
        """A currency present in the report without full monthly coverage fails cleanly."""
        handler = self._make_aws_handler()
        handler.currency = "EUR"
        # Months outside the rates seeded for the test tenant.
        handler.start_datetime = datetime(2026, 1, 1)
        handler.end_datetime = datetime(2026, 2, 28)
        handler.__dict__["raw_currencies_for_conversion"] = {"GBP"}
        self._create_rates("GBP", "EUR", {date(2026, 1, 1): Decimal("1.17")})

        with tenant_context(handler.tenant), self.assertRaises(ExchangeRateNotFound):
            handler.monthly_exchange_rate_map

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.queries.get_monthly_exchange_rate_map", return_value={})
    def test_rate_map_loaded_once_per_request(self, mock_rate_map, _):
        """The annotation and the response coverage check share one rate lookup."""
        handler = self._make_aws_handler()
        handler.__dict__["raw_currencies_for_conversion"] = set()
        handler.exchange_rate_annotation_dict
        handler._initialize_response_output(handler.parameters)
        mock_rate_map.assert_called_once()
