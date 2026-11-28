#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Generated database invariants for COST-8584 scoped currency discovery."""
import json
from datetime import date
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django_tenants.utils import tenant_context
from hypothesis import given
from hypothesis import seed
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase
from hypothesis.statistics import collector
from model_bakery import baker

from api.currency.exceptions import ExchangeRateNotFound
from api.models import Provider
from api.report.test import test_currency_discovery as fixtures
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import MonthlyExchangeRate
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.models import TenantAPIProvider
from reporting.provider.ocp.models import OCPCostSummaryP


class CurrencyDiscoveryProperties(fixtures.CurrencySnapshotTestCase, HypothesisTestCase):
    """Compare real discovery with independent generated fixture membership."""

    ocp_row = fixtures.CurrencyDiscoveryTest.ocp_row
    ocp_handler = fixtures.CurrencyDiscoveryTest.ocp_handler
    aws_handler = fixtures.CurrencyDiscoveryTest.aws_handler
    aws_row = fixtures.CurrencyDiscoveryTest.aws_row
    rate = fixtures.CurrencyDiscoveryTest.rate

    def run(self, result=None):
        def record(stats):
            cases = stats["generate-phase"]["test-cases"]
            print(
                "COST8584_PROPERTY "
                + json.dumps(
                    {
                        "test": self.id(),
                        "seed": 8584,
                        "valid": sum(case["status"] == "valid" for case in cases),
                        "failing": sum(case["status"] == "interesting" for case in cases),
                    }
                ),
                flush=True,
            )

        with collector.with_value(record):
            return super().run(result)

    def setUp(self):
        super().setUp()
        self.enterContext(patch("api.report.queries.is_currency_discovery_optimization_enabled", return_value=True))
        with tenant_context(self.tenant):
            EnabledTagKeys.objects.get_or_create(key="product", provider_type=Provider.PROVIDER_OCP)

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(
        st.lists(
            st.tuples(st.sampled_from([None, "USD", "EUR", "GBP"]), st.booleans(), st.booleans()),
            min_size=0,
            max_size=8,
        )
    )
    def test_discovery_equals_generated_row_membership(self, records):
        with tenant_context(self.tenant):
            sources, currencies = set(), set()
            for currency, in_cluster, in_month in records:
                source = uuid4()
                day = date(2026, 10, 5) if in_month else date(2026, 9, 5)
                cluster = "cc-alpha" if in_cluster else "cc-beta"
                self.ocp_row(
                    source_uuid=source,
                    raw_currency=currency,
                    cluster_id=cluster,
                    cluster_alias=cluster,
                    usage_start=day,
                    usage_end=day,
                )
                if in_cluster and in_month:
                    sources.add(source)
                    if currency is not None:
                        currencies.add(currency)
            handler = self.ocp_handler()
            self.assertEqual(handler.source_uuids_for_conversion, sources)
            self.assertEqual(handler.raw_currencies_for_conversion, currencies)

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(st.sampled_from(["EUR", "SGD", "JPY"]), st.integers(min_value=1, max_value=100))
    def test_unrelated_model_does_not_change_report_or_error(self, currency, amount):
        with tenant_context(self.tenant), patch(
            "api.report.queries.is_feature_flag_enabled_by_schema", return_value=True
        ), patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True):
            row = self.ocp_row(infrastructure_raw_cost=Decimal(amount))
            before = self.ocp_handler().execute_query()
            model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency=currency)
            baker.make(CostModelMap, cost_model=model, provider_uuid=uuid4())
            handler = self.ocp_handler()
            self.assertNotIn(row.source_uuid, handler.request_source_to_currency_map)
            self.assertIn(currency, handler.request_source_to_currency_map.values())
            self.assertEqual(handler.execute_query(), before)
            self.assertEqual(before["total"]["cost"]["total"]["value"], Decimal(amount))

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(st.sampled_from(["USD", "EUR", "GBP"]), st.lists(st.sampled_from(["USD", "SGD", "JPY"]), max_size=3))
    def test_summary_ghosts_do_not_change_raw_membership(self, currency, ghosts):
        with tenant_context(self.tenant):
            row = self.ocp_row(raw_currency=currency)
            for ghost_currency in ghosts:
                source = baker.make(TenantAPIProvider, name="cc8584-property-ghost", type=Provider.PROVIDER_OCP)
                baker.make(
                    OCPCostSummaryP,
                    id=uuid4(),
                    source_uuid=source,
                    raw_currency=ghost_currency,
                    cluster_id="cc-alpha",
                    cluster_alias="cc-alpha",
                    usage_start=date(2026, 10, 5),
                    usage_end=date(2026, 10, 5),
                )
            handler = self.ocp_handler()
            self.assertEqual(handler.source_uuids_for_conversion, {row.source_uuid})
            self.assertEqual(handler.raw_currencies_for_conversion, {currency})

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(st.sampled_from([None, "USD"]), st.integers(min_value=0, max_value=100))
    def test_duplicates_preserve_identities_and_double_cost(self, currency, amount):
        with tenant_context(self.tenant), patch(
            "api.report.queries.is_feature_flag_enabled_by_schema", return_value=True
        ), patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True):
            self.ocp_row(source_uuid=None, raw_currency=currency, infrastructure_raw_cost=Decimal(amount))
            first = self.ocp_handler()
            expected = set() if currency is None else {"USD"}
            self.assertEqual(first.raw_currencies_for_conversion, expected)
            self.assertEqual(first.execute_query()["total"]["cost"]["total"]["value"], Decimal(amount))
            self.ocp_row(source_uuid=None, raw_currency=currency, infrastructure_raw_cost=Decimal(amount))
            second = self.ocp_handler()
            self.assertEqual(second.source_uuids_for_conversion, set())
            self.assertEqual(second.raw_currencies_for_conversion, expected)
            self.assertEqual(second.execute_query()["total"]["cost"]["total"]["value"], Decimal(amount * 2))

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(
        st.sampled_from(["EUR", "GBP"]),
        st.integers(1, 1000),
        st.integers(1, 1000),
        st.integers(1, 5000),
        st.booleans(),
    )
    def test_previous_month_amounts_and_missing_rates(self, currency, current, previous, mills, missing):
        """S04/S09/S11: generated temporal membership, amounts and errors."""
        with tenant_context(self.tenant), patch(
            "api.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=timezone.utc)
        ), patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True):
            from reporting.provider.aws.models import AWSEnabledCategoryKeys

            AWSEnabledCategoryKeys.objects.update_or_create(key="CostCenter", defaults={"enabled": True})
            MonthlyExchangeRate.objects.all().delete()
            factor = Decimal(mills) / Decimal("1000")
            self.aws_row("USD", date(2026, 11, 5), unblended_cost=Decimal(current))
            self.aws_row(currency, date(2026, 10, 5), unblended_cost=Decimal(previous))
            self.rate(currency, str(factor), date(2026, 11, 1))
            if not missing:
                self.rate(currency, str(factor), date(2026, 10, 1))
            handler = self.aws_handler(
                "delta=cost&filter[resolution]=daily&filter[time_scope_units]=month&"
                "filter[time_scope_value]=-1&filter[aws_category:CostCenter]=cc8584"
            )
            self.assertEqual(handler.raw_currencies_for_conversion, {"USD", currency})
            if missing:
                with self.assertRaises(ExchangeRateNotFound) as raised:
                    handler.execute_query()
                self.assertIn("2026-10", str(raised.exception.detail["currency"]))
            else:
                response = handler.execute_query()
                expected_delta = Decimal(current) - Decimal(previous) * factor
                self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal(current))
                self.assertEqual(response["delta"]["value"], expected_delta)
                day = next(day for day in response["data"] if day["date"] == "2026-11-05")
                self.assertEqual(day["values"][0]["delta_value"], expected_delta)

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(
        st.sampled_from(["EUR", "SGD"]),
        st.sampled_from(["GBP", "JPY"]),
        st.integers(1, 500),
        st.integers(0, 100),
        st.integers(1, 5000),
        st.booleans(),
        st.booleans(),
        st.booleans(),
        st.booleans(),
    )
    def test_metadata_coverage_and_snapshot_preserve_money(
        self, currency, unrelated, amount, infra, mills, complete, november, mutate, duplicate
    ):
        """Generate complete/fallback coverage, rate snapshots and exact amounts."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from api.report.ocp.query_handler import OCPReportQueryHandler
        from api.report.ocp.view import OCPCostView
        from api.report.test import test_currency_discovery_reports as reference

        with tenant_context(self.tenant), patch(
            "api.report.queries.is_feature_flag_enabled_by_schema", return_value=True
        ), patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True):
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            source = uuid4()
            model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency=currency)
            baker.make(CostModelMap, provider_uuid=source, cost_model=model)
            if duplicate:
                duplicate_model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency="USD")
                baker.make(CostModelMap, provider_uuid=source, cost_model=duplicate_model)
            other_model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency=unrelated)
            baker.make(CostModelMap, provider_uuid=uuid4(), cost_model=other_model)
            for month in [date(2026, 10, 1), date(2026, 11, 1)]:
                factor = Decimal(mills + (100 if month.month == 11 else 0)) / Decimal("1000")
                self.rate(currency, str(factor), month)
                if complete:
                    self.rate(unrelated, "0.75", month)
            day = date(2026, 11 if november else 10, 5)
            self.ocp_row(
                source_uuid=source,
                usage_start=day,
                usage_end=day,
                infrastructure_raw_cost=Decimal(infra),
                raw_currency="USD",
                cost_model_cpu_cost=Decimal(amount),
                cost_model_rate_type="Supplementary",
            )
            params = self.mocked_query_params(
                "?start_date=2026-10-01&end_date=2026-11-09&filter[cluster]=cc-alpha&group_by[tag:product]=*",
                OCPCostView,
                path="/api/cost-management/v1/reports/openshift/costs/",
            )
            handler = OCPReportQueryHandler(params)
            legacy = reference.LegacyOCP(params)
            legacy.monthly_exchange_rate_map
            with CaptureQueriesContext(connection) as captured:
                mapping = handler.request_source_to_currency_map
            fact_reads = [q["sql"] for q in captured if "reporting_ocpusagelineitem_daily_summary" in q["sql"]]
            self.assertEqual(fact_reads, [])
            self.assertEqual(mapping[source], currency)
            self.assertEqual(len(mapping), 2)
            if mutate:
                MonthlyExchangeRate.objects.filter(base_currency=currency).update(exchange_rate=Decimal("9"))
            with CaptureQueriesContext(connection) as captured:
                actual = handler.execute_query()
            self.assertFalse(any("monthly_exchange_rate" in q["sql"].lower() for q in captured))
            self.assertEqual(actual, legacy.execute_query())
            expected_factor = Decimal(mills + (100 if november else 0)) / Decimal("1000")
            self.assertEqual(
                actual["total"]["cost"]["total"]["value"], Decimal(infra) + Decimal(amount) * expected_factor
            )
            if mutate:
                fresh = OCPReportQueryHandler(params).execute_query()
                self.assertEqual(
                    fresh["total"]["cost"]["total"]["value"], Decimal(infra) + Decimal(amount) * Decimal("9")
                )

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(st.booleans(), st.booleans(), st.booleans(), st.integers(0, 500))
    def test_required_raw_or_model_rate_errors_survive_metadata(self, raw, gap, november, amount):
        """Generated missing base/month coverage must never become rate one."""
        from api.report.ocp.query_handler import OCPReportQueryHandler
        from api.report.ocp.view import OCPCostView

        with tenant_context(self.tenant), patch(
            "api.report.queries.is_feature_flag_enabled_by_schema", return_value=True
        ), patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True):
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            source = uuid4()
            currency = "GBP" if raw else "EUR"
            model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency="USD" if raw else currency)
            baker.make(CostModelMap, provider_uuid=source, cost_model=model)
            other = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency="JPY")
            baker.make(CostModelMap, provider_uuid=uuid4(), cost_model=other)
            if gap:
                self.rate(currency, "1.20", date(2026, 11, 1))
            day = date(2026, 11 if november else 10, 5)
            self.ocp_row(
                source_uuid=source,
                raw_currency=currency if raw else "USD",
                usage_start=day,
                usage_end=day,
                infrastructure_raw_cost=Decimal(amount if raw else 0),
                cost_model_cpu_cost=Decimal(0 if raw else amount),
                cost_model_rate_type="Supplementary",
            )
            handler = OCPReportQueryHandler(
                self.mocked_query_params(
                    "?start_date=2026-10-01&end_date=2026-11-09&filter[cluster]=cc-alpha&group_by[tag:product]=*",
                    OCPCostView,
                    path="/api/cost-management/v1/reports/openshift/costs/",
                )
            )
            with self.assertRaises(ExchangeRateNotFound) as raised:
                handler.execute_query()
            self.assertEqual(raised.exception.status_code, 400)
            detail = str(raised.exception.detail["currency"])
            self.assertIn(currency + " -> USD", detail)
            self.assertIn("2026-10", detail)
            self.assertNotIn("JPY", detail)

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(st.sampled_from(["EUR", "SGD"]), st.booleans(), st.booleans(), st.integers(1, 500), st.integers(0, 100))
    def test_unmapped_model_amounts_keep_identity_default(self, currency, complete, null_source, amount, infra):
        """Absent source mappings cannot borrow another source's currency or lose cost."""
        from api.report.test import test_currency_discovery_reports as reference

        with tenant_context(self.tenant), patch(
            "api.report.queries.is_feature_flag_enabled_by_schema", return_value=True
        ), patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True):
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency=currency)
            baker.make(CostModelMap, provider_uuid=uuid4(), cost_model=model)
            if complete:
                self.rate(currency, "1.20")
            self.ocp_row(
                source_uuid=None if null_source else uuid4(),
                raw_currency="USD",
                infrastructure_raw_cost=Decimal(infra),
                cost_model_cpu_cost=Decimal(amount),
                cost_model_rate_type="Supplementary",
            )
            handler = self.ocp_handler()
            response = handler.execute_query()
            self.assertEqual(response, reference.LegacyOCP(handler.parameters).execute_query())
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal(infra) + Decimal(amount))

    @seed(8584)
    @settings(max_examples=100, deadline=None, database=None)
    @given(st.sampled_from(["GBP", "USD", None]), st.integers(0, 1000), st.integers(1, 50000), st.booleans())
    def test_large_rate_snapshot_preserves_decimal_money(self, currency, amount, mills, missing):
        """Large snapshots preserve precise factors, identity, NULL and rate errors."""
        from api.currency.currencies import get_active_iso_currency_codes
        from api.report.test.test_currency_discovery_reports import LegacyOCP

        with tenant_context(self.tenant), patch(
            "api.report.queries.is_feature_flag_enabled_by_schema", return_value=True
        ), patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True):
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            for code in sorted(get_active_iso_currency_codes() - {"USD", "EUR", "GBP", "SGD"})[:40]:
                self.rate(code, "1.23456789")
            factor = Decimal(mills) / Decimal("10000")
            if not missing:
                self.rate("GBP", str(factor))
            self.ocp_row(
                source_uuid=None,
                raw_currency=currency,
                infrastructure_raw_cost=Decimal(amount),
                cost_model_cpu_cost=Decimal("0"),
                cost_model_rate_type="Supplementary",
            )
            handler = self.ocp_handler()
            if currency == "GBP" and missing:
                with self.assertRaises(ExchangeRateNotFound) as error:
                    handler.execute_query()
                self.assertEqual(error.exception.status_code, 400)
                self.assertIn("GBP -> USD", str(error.exception.detail))
            else:
                response = handler.execute_query()
                expected = Decimal(amount) * (factor if currency == "GBP" else Decimal("1"))
                self.assertEqual(response["total"]["cost"]["total"]["value"], expected)
                self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
