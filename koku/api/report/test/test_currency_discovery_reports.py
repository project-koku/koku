#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Real report and provider contracts for COST-8584."""
from datetime import date
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from functools import cached_property
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.db.models import Q
from django.test import override_settings
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import tenant_context
from model_bakery import baker

from api.currency.models import ExchangeRateDictionary
from api.iam.test.iam_test_case import Tenant
from api.models import Provider
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
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from api.report.test import test_currency_discovery as fixtures
from cost_models.models import CostModelMap
from cost_models.models import MonthlyExchangeRate
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.aws.models import AWSEnabledCategoryKeys


class LegacyDiscovery:
    """Frozen upstream discovery recipe as a real-SQL response reference.

    Only the reference handler uses this recipe; the actual handler is never
    patched. All remaining report operations execute normally on PostgreSQL.
    """

    @property
    def currency_discovery_optimization_enabled(self):
        """Keep the reference on upstream recipes even when the real flag is ON."""
        return False

    def _conversion_queryset_values(self, field_name):
        values = set(self.conversion_queryset.values_list(field_name, flat=True).distinct())
        if self.include_previous_period_for_conversion:
            values |= set(self.previous_conversion_queryset.values_list(field_name, flat=True).distinct())
        return values - {None}

    @cached_property
    def request_source_to_currency_map(self):
        mapping = CostModelMap.objects.filter(provider_uuid__in=self.source_uuids_for_conversion).values(
            "provider_uuid", "cost_model__currency"
        )
        return {r["provider_uuid"]: r["cost_model__currency"] for r in mapping if r["cost_model__currency"]}


class LegacyOCP(LegacyDiscovery, OCPReportQueryHandler):
    """Upstream OCP discovery with the complete real report pipeline."""


class LegacyAWS(LegacyDiscovery, AWSReportQueryHandler):
    """Upstream AWS discovery with the complete real report pipeline."""


class CurrencyDiscoveryReports(fixtures.CurrencySnapshotTestCase):
    """Compare monetary values and whole responses, not just query syntax."""

    ocp_row = fixtures.CurrencyDiscoveryTest.ocp_row
    ocp_handler = fixtures.CurrencyDiscoveryTest.ocp_handler
    aws_row = fixtures.CurrencyDiscoveryTest.aws_row
    aws_handler = fixtures.CurrencyDiscoveryTest.aws_handler
    rate = fixtures.CurrencyDiscoveryTest.rate

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            EnabledTagKeys.objects.get_or_create(key="product", provider_type=Provider.PROVIDER_OCP)
            AWSEnabledCategoryKeys.objects.update_or_create(key="CostCenter", defaults={"enabled": True})
            MonthlyExchangeRate.objects.all().delete()
            CostModelMap.objects.all().delete()

    @patch("api.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=timezone.utc))
    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    def test_delta_amounts_use_both_monthly_rates(self, _flag, _clock):
        """S11: equal base amounts use their own month rates before delta."""
        with tenant_context(self.tenant):
            self.aws_row("EUR", date(2026, 10, 5))
            self.aws_row("EUR", date(2026, 11, 5))
            self.rate("EUR", "1.10", date(2026, 10, 1))
            self.rate("EUR", "1.20", date(2026, 11, 1))
            handler = self.aws_handler(
                "delta=cost&filter[resolution]=daily&filter[time_scope_units]=month&"
                "filter[time_scope_value]=-1&filter[aws_category:CostCenter]=cc8584"
            )
            response = handler.execute_query()
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("120"))
            self.assertEqual(response["delta"]["value"], Decimal("10"))

    @patch("api.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=timezone.utc))
    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True)
    def test_real_chart_and_table_reports_preserve_response(self, _ocp, _base, _clock):
        """S12: complete chart/table and AWS delta responses equal upstream."""
        with tenant_context(self.tenant):
            for n in range(1, 9):
                self.ocp_row(source_uuid=None, all_labels={"product": f"v-{n}"}, infrastructure_raw_cost=Decimal(n))
            for suffix in ["&filter[limit]=5", "&filter[offset]=0&order_by[cost]=desc"]:
                params = self.mocked_query_params(
                    "?start_date=2026-10-01&end_date=2026-10-31&filter[cluster]=cc-alpha&"
                    "group_by[tag:product]=*" + suffix,
                    OCPCostView,
                    path="/api/cost-management/v1/reports/openshift/costs/",
                )
                response = OCPReportQueryHandler(params).execute_query()
                self.assertEqual(response, LegacyOCP(params).execute_query())
                self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("36"))
            self.aws_row("EUR", date(2026, 10, 5))
            self.aws_row("EUR", date(2026, 11, 5))
            self.rate("EUR", "1.10", date(2026, 10, 1))
            self.rate("EUR", "1.20", date(2026, 11, 1))
            handler = self.aws_handler(
                "delta=cost&filter[resolution]=daily&filter[time_scope_units]=month&"
                "filter[time_scope_value]=-1&filter[aws_category:CostCenter]=cc8584"
            )
            self.assertEqual(handler.execute_query(), LegacyAWS(handler.parameters).execute_query())

    def test_tenants_and_flag_off_path_are_unchanged(self):
        """S13: the same UUID in another tenant cannot alter this report."""
        other = Tenant.objects.get(schema_name="org2222222")
        source = uuid4()
        with tenant_context(other):
            self.ocp_row(source_uuid=source, infrastructure_raw_cost=Decimal("999"))
        dictionary = ExchangeRateDictionary.objects.first()
        if dictionary is None:
            dictionary = ExchangeRateDictionary.objects.create(currency_exchange_dictionary={"USD": {"USD": 1}})
        else:
            dictionary.currency_exchange_dictionary = {"USD": {"USD": 1}}
            dictionary.save()
        with tenant_context(self.tenant):
            self.ocp_row(source_uuid=source, infrastructure_raw_cost=Decimal("10"))
            for enabled in [True, False]:
                with self.subTest(constant_currency=enabled), patch(
                    "api.report.queries.is_feature_flag_enabled_by_schema", return_value=enabled
                ), patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=enabled):
                    handler = self.ocp_handler()
                    with CaptureQueriesContext(connection) as queries:
                        response = handler.execute_query()
                    self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("10"))
                    self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
                    if not enabled:
                        self.assertFalse(any("monthly_exchange_rate" in q["sql"] for q in queries))

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.queries.is_currency_discovery_optimization_enabled", return_value=True)
    def test_shared_helper_provider_and_deployment_parity(self, _new_flag, _cc_flag):
        """S14: actual provider querysets retain scoped currency membership."""
        variants = [
            (AWSReportQueryHandler, AWSCostView),
            (AzureReportQueryHandler, AzureCostView),
            (GCPReportQueryHandler, GCPCostView),
            (OCPReportQueryHandler, OCPCostView),
            (OCPAWSReportQueryHandler, OCPAWSCostView),
            (OCPAzureReportQueryHandler, OCPAzureCostView),
            (OCPGCPReportQueryHandler, OCPGCPCostView),
        ]
        with tenant_context(self.tenant):
            for cls, view in variants:
                with self.subTest(provider=cls.__name__):
                    handler = cls(self.mocked_query_params("?start_date=2026-10-01&end_date=2026-10-31", view))
                    field = handler._mapper.cost_units_key
                    row = baker.make(
                        handler.query_table,
                        usage_start=date(2026, 10, 5),
                        usage_end=date(2026, 10, 5),
                        **{field: "USD"},
                    )
                    handler.query_filter = Q(pk=row.pk)
                    handler.query_exclusions = None
                    self.assertEqual(handler.raw_currencies_for_conversion, {"USD"})
                    expected = set(handler.conversion_queryset.values_list(field, flat=True).distinct()) - {None}
                    self.assertEqual(handler.raw_currencies_for_conversion, expected)
            self.ocp_row(raw_currency="USD")
            for onprem in [True, False]:
                with self.subTest(onprem=onprem), override_settings(ONPREM=onprem):
                    self.assertEqual(self.ocp_handler().raw_currencies_for_conversion, {"USD"})


class CurrencyMetadataDiscovery(fixtures.CurrencySnapshotTestCase):
    """V3 contracts exercise actual metadata, discovery and complete reports."""

    ocp_row = fixtures.CurrencyDiscoveryTest.ocp_row
    rate = fixtures.CurrencyDiscoveryTest.rate

    def setUp(self):
        super().setUp()
        self.enterContext(patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True))
        self.enterContext(patch("api.report.queries.is_currency_discovery_optimization_enabled", return_value=True))
        self.enterContext(patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True))
        self.enterContext(patch("api.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=timezone.utc)))
        with tenant_context(self.tenant):
            EnabledTagKeys.objects.get_or_create(key="product", provider_type=Provider.PROVIDER_OCP)
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            self.sources = []
            for currency in ["EUR", "EUR", "EUR", "SGD", "SGD", "USD", "USD"]:
                from cost_models.models import CostModel

                model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency=currency)
                source = uuid4()
                baker.make(CostModelMap, provider_uuid=source, cost_model=model)
                self.sources.append(source)
            for month, eur in [(date(2026, 10, 1), "1.10"), (date(2026, 11, 1), "1.20")]:
                self.rate("EUR", eur, month)
                self.rate("SGD", "0.75", month)
                self.rate("GBP", "1.25", month)
            # The default report covers October; use 1.20 for its exact 245 case.
            self.rate("EUR", "1.20")

    def handler(self, extra="", relative=False):
        dates = (
            "filter[resolution]=daily&filter[time_scope_units]=month&filter[time_scope_value]=-1"
            if relative
            else "start_date=2026-10-01&end_date=2026-10-31"
        )
        params = self.mocked_query_params(
            "?" + dates + "&filter[cluster]=cc-alpha&group_by[tag:product]=*" + extra,
            OCPCostView,
            path="/api/cost-management/v1/reports/openshift/costs/",
        )
        return OCPReportQueryHandler(params)

    def dual_row(self, **extra):
        values = {
            "source_uuid": self.sources[0],
            "raw_currency": "GBP",
            "infrastructure_raw_cost": Decimal("100"),
            "cost_model_cpu_cost": Decimal("100"),
            "cost_model_rate_type": "Supplementary",
        }
        values.update(extra)
        return self.ocp_row(**values)

    def source_reads(self, captured):
        reads = []
        for query in captured:
            sql = query["sql"].strip()
            discovery = sql.upper().startswith("SELECT DISTINCT ") or sql.upper().startswith("WITH DISCOVERY_ROWS(")
            if discovery and "reporting_ocpusagelineitem_daily_summary" in sql and '"source_uuid"' in sql:
                reads.append(sql)
        return reads

    def test_complete_coverage_avoids_fact_source_discovery(self):
        """M01: populated complete metadata needs no fact source enumeration."""
        with tenant_context(self.tenant):
            self.dual_row()
            handler = self.handler()
            with CaptureQueriesContext(connection) as captured:
                mapping = handler.request_source_to_currency_map
                handler._get_base_currencies_for_conversion()
                handler.exchange_rate_annotation_dict
                handler._initialize_response_output(handler.parameters)
                handler._cost_model_currency_case()
            self.assertEqual(self.source_reads(captured), [], "Complete coverage must not enumerate fact sources")
            self.assertEqual(len(mapping), 7)
            self.assertEqual(handler._get_base_currencies_for_conversion(), {"USD", "EUR", "SGD", "GBP"})

    def test_complete_coverage_preserves_exact_report_response(self):
        """M02: extra covered source CASE branches cannot change selected rows."""
        with tenant_context(self.tenant):
            self.dual_row()
            for suffix in ["", "&filter[limit]=5", "&filter[offset]=0&order_by[cost]=desc"]:
                handler = self.handler(suffix)
                actual = handler.execute_query()
                expected = LegacyOCP(handler.parameters).execute_query()
                self.assertEqual(actual, expected)
                self.assertEqual(actual["total"]["cost"]["total"]["value"], Decimal("245"))
                self.assertEqual(actual["total"]["infrastructure"]["total"]["value"], Decimal("125"))
                self.assertEqual(actual["total"]["supplementary"]["total"]["value"], Decimal("120"))

    def test_incomplete_unrelated_coverage_succeeds_without_discovery(self):
        """M03/C03: validate actual inputs in the aggregation, without discovery."""
        with tenant_context(self.tenant):
            self.dual_row()
            MonthlyExchangeRate.objects.filter(base_currency="SGD", effective_date=date(2026, 10, 1)).delete()
            handler = self.handler()
            with CaptureQueriesContext(connection) as captured:
                mapping = handler.request_source_to_currency_map
            self.assertEqual(self.source_reads(captured), [])
            self.assertEqual(len(mapping), 7)
            self.assertEqual(mapping[self.sources[0]], "EUR")
            response = handler.execute_query()
            self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))

    def test_required_missing_coverage_preserves_error(self):
        """M04: required prior-month coverage remains an HTTP 400 error."""
        from api.currency.exceptions import ExchangeRateNotFound

        with tenant_context(self.tenant):
            self.dual_row(raw_currency=None, infrastructure_raw_cost=Decimal("0"))
            self.dual_row(
                raw_currency=None,
                infrastructure_raw_cost=Decimal("0"),
                usage_start=date(2026, 11, 5),
                usage_end=date(2026, 11, 5),
            )
            MonthlyExchangeRate.objects.filter(
                base_currency__in=["EUR", "SGD"], effective_date=date(2026, 10, 1)
            ).delete()
            with self.assertRaises(ExchangeRateNotFound) as raised:
                self.handler("&delta=cost", relative=True).execute_query()
            self.assertEqual(raised.exception.status_code, 400)
            detail = str(raised.exception.detail["currency"])
            self.assertIn("EUR -> USD", detail)
            self.assertIn("2026-10", detail)
            self.assertNotIn("SGD", detail)

    def test_metadata_fast_path_uses_previous_period_rates(self):
        """M05: previous-only sources use their own loaded monthly factor."""
        with tenant_context(self.tenant):
            self.rate("EUR", "1.10")
            self.dual_row(raw_currency=None, infrastructure_raw_cost=Decimal("0"))
            self.dual_row(
                source_uuid=self.sources[1],
                raw_currency=None,
                infrastructure_raw_cost=Decimal("0"),
                usage_start=date(2026, 11, 5),
                usage_end=date(2026, 11, 5),
            )
            handler = self.handler("&delta=cost", relative=True)
            with CaptureQueriesContext(connection) as captured:
                handler.monthly_exchange_rate_map
            self.assertEqual(self.source_reads(captured), [])
            response = handler.execute_query()
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("120"))
            self.assertEqual(response["delta"]["value"], Decimal("10"))

    def test_rate_snapshot_is_reused_by_all_consumers(self):
        """M06: rates used for eligibility are the rates used for amounts."""
        with tenant_context(self.tenant):
            self.dual_row()
            handler = self.handler()
            legacy = LegacyOCP(handler.parameters)
            legacy.monthly_exchange_rate_map
            handler.request_source_to_currency_map
            MonthlyExchangeRate.objects.filter(base_currency="EUR", effective_date=date(2026, 10, 1)).update(
                exchange_rate=Decimal("9")
            )
            MonthlyExchangeRate.objects.filter(base_currency="SGD").delete()
            with CaptureQueriesContext(connection) as captured:
                actual = handler.execute_query()
                handler._cost_model_currency_case()
            rate_reads = [q["sql"] for q in captured if "monthly_exchange_rate" in q["sql"].lower()]
            self.assertEqual(rate_reads, [], "Eligibility and annotations must share the loaded rate snapshot")
            self.assertEqual(actual, legacy.execute_query())
            self.assertEqual(actual["total"]["cost"]["total"]["value"], Decimal("245"))
            fresh = self.handler().execute_query()
            self.assertEqual(fresh["total"]["cost"]["total"]["value"], Decimal("1025"))

    def test_complete_coverage_csv_preserves_audit_columns(self):
        """M07: CSV keeps model fallback and raw-infrastructure precedence."""
        with tenant_context(self.tenant):
            for namespace, raw, infra, total, base, factor in [
                ("metadata-standalone", None, "0", "120", "EUR", "1.20"),
                ("metadata-cloud", "GBP", "100", "245", "GBP", "1.25"),
            ]:
                with self.subTest(namespace=namespace):
                    self.dual_row(namespace=namespace, raw_currency=raw, infrastructure_raw_cost=Decimal(infra))
                    handler = self.handler("&filter[project]=" + namespace)
                    handler.is_csv_output = True
                    with CaptureQueriesContext(connection) as captured:
                        response = handler.execute_query()
                    self.assertEqual(self.source_reads(captured), [])
                    self.assertTrue(response["data"])
                    for row in response["data"]:
                        self.assertEqual(row["base_currency"], base)
                        self.assertEqual(row["exchange_rate"], Decimal(factor))
                    self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal(total))

    def test_raw_missing_currency_is_not_hidden_by_model_coverage(self):
        """M11: complete model coverage cannot hide a required raw rate gap."""
        from api.currency.exceptions import ExchangeRateNotFound

        with tenant_context(self.tenant):
            self.dual_row()
            MonthlyExchangeRate.objects.filter(base_currency="GBP").delete()
            with self.assertRaises(ExchangeRateNotFound) as raised:
                self.handler().execute_query()
            self.assertIn("GBP -> USD", str(raised.exception.detail["currency"]))

    def test_metadata_flag_defaults_off_and_preserves_legacy(self):
        """M08: require both flags; missing flags and on-prem defaults remain OFF."""
        from koku.feature_flags import MockUnleashClient, fallback_development_true
        from masu.processor import CONSTANT_CURRENCY_FLAG, CURRENCY_DISCOVERY_OPTIMIZATION_FLAG

        client = MockUnleashClient("koku", "development", "metadata-test")
        self.assertFalse(client.is_enabled(CURRENCY_DISCOVERY_OPTIMIZATION_FLAG, {}, fallback_development_true))
        dictionary, _ = ExchangeRateDictionary.objects.get_or_create(pk=1)
        dictionary.currency_exchange_dictionary = {
            "GBP": {"USD": Decimal("1.25")},
            "EUR": {"USD": Decimal("1.20")},
            "SGD": {"USD": Decimal("0.75")},
        }
        dictionary.save()
        with tenant_context(self.tenant):
            self.dual_row()
            for onprem in [False, True]:
                for constant in [False, True]:
                    for optimization in [False, True]:

                        def flags(schema, flag, **kwargs):
                            return {
                                CONSTANT_CURRENCY_FLAG: constant,
                                CURRENCY_DISCOVERY_OPTIMIZATION_FLAG: optimization,
                            }.get(flag, False)

                        with self.subTest(
                            onprem=onprem, constant=constant, optimization=optimization
                        ), override_settings(ONPREM=onprem), patch(
                            "api.report.queries.is_feature_flag_enabled_by_schema", side_effect=flags
                        ), patch(
                            "api.report.queries.is_currency_discovery_optimization_enabled", return_value=optimization
                        ), patch(
                            "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", side_effect=flags
                        ):
                            handler = self.handler()
                            with CaptureQueriesContext(connection) as captured:
                                response = handler.execute_query()
                            self.assertEqual(
                                handler.currency_discovery_optimization_enabled, constant and optimization
                            )
                            self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
                            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))
                            if not constant:
                                self.assertFalse(any("monthly_exchange_rate" in q["sql"].lower() for q in captured))
                            elif optimization:
                                self.assertEqual(self.source_reads(captured), [])
                            else:
                                self.assertTrue(self.source_reads(captured))

    def test_metadata_scope_empty_null_and_tenant_isolation(self):
        """M09: other schemas and denied rows cannot change eligibility or amounts."""
        from cost_models.models import CostModel

        other = Tenant.objects.get(schema_name="org2222222")
        with tenant_context(other):
            model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency="JPY")
            baker.make(CostModelMap, provider_uuid=self.sources[0], cost_model=model)
            self.dual_row(raw_currency="JPY", infrastructure_raw_cost=Decimal("999"))
        with tenant_context(self.tenant):
            self.dual_row()
            self.dual_row(source_uuid=uuid4(), raw_currency="JPY", namespace="metadata-denied")
            baker.make(CostModelMap, provider_uuid=uuid4(), cost_model=None)
            empty_model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency="")
            baker.make(CostModelMap, provider_uuid=uuid4(), cost_model=empty_model)
            handler = self.handler("&exclude[project]=metadata-denied")
            with CaptureQueriesContext(connection) as captured:
                mapping = handler.request_source_to_currency_map
                response = handler.execute_query()
            self.assertEqual(len(mapping), 7)
            self.assertNotIn("JPY", mapping.values())
            self.assertEqual(self.source_reads(captured), [])
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))
            self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
            empty = self.handler()
            legacy = LegacyOCP(empty.parameters)
            empty.query_filter = legacy.query_filter = Q(pk__in=[])
            self.assertEqual(empty.execute_query(), legacy.execute_query())

    def test_metadata_duplicate_mapping_precedence_matches_legacy(self):
        """M10: preserve the older mapping winner under existing -id ordering."""
        from cost_models.models import CostModel

        with tenant_context(self.tenant):
            self.dual_row()
            newer = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency="USD")
            baker.make(CostModelMap, provider_uuid=self.sources[0], cost_model=newer)
            for complete in [True, False]:
                with self.subTest(complete=complete):
                    if not complete:
                        MonthlyExchangeRate.objects.filter(
                            base_currency="SGD", effective_date=date(2026, 10, 1)
                        ).delete()
                    handler = self.handler()
                    self.assertEqual(handler.request_source_to_currency_map[self.sources[0]], "EUR")
                    response = handler.execute_query()
                    self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))
                    self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())

    def test_nondefault_target_currency_preserves_direction_and_identity(self):
        """M02/M03: target EUR identities and foreign rates retain their direction."""
        with tenant_context(self.tenant):
            self.dual_row()
            for currency, factor in [("USD", "0.80"), ("SGD", "0.60"), ("GBP", "1.10")]:
                MonthlyExchangeRate.objects.create(
                    base_currency=currency,
                    target_currency="EUR",
                    effective_date=date(2026, 10, 1),
                    exchange_rate=Decimal(factor),
                    rate_type="static",
                )
            for complete in [True, False]:
                with self.subTest(complete=complete):
                    if not complete:
                        MonthlyExchangeRate.objects.filter(base_currency="SGD", target_currency="EUR").delete()
                    handler = self.handler("&currency=EUR")
                    response = handler.execute_query()
                    self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
                    self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("210"))
                    self.assertEqual(response["total"]["cost"]["total"]["units"], "EUR")

    def test_unmapped_source_keeps_existing_currency_defaults(self):
        """M09: unrelated covered mappings cannot assign a currency to a new UUID."""
        with tenant_context(self.tenant):
            self.dual_row(source_uuid=uuid4(), raw_currency="USD", infrastructure_raw_cost=Decimal("10"))
            handler = self.handler()
            with CaptureQueriesContext(connection) as captured:
                response = handler.execute_query()
            self.assertEqual(self.source_reads(captured), [])
            self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("110"))


class CurrencyAggregateCoverageTest(fixtures.CurrencySnapshotTestCase):
    """C01-C07: aggregate coverage executes real report SQL."""

    def setUp(self):
        super().setUp()
        self.enterContext(patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True))
        self.enterContext(patch("api.report.queries.is_currency_discovery_optimization_enabled", return_value=True))
        self.enterContext(patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True))
        self.enterContext(patch("api.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=timezone.utc)))
        with tenant_context(self.tenant):
            EnabledTagKeys.objects.get_or_create(key="product", provider_type=Provider.PROVIDER_OCP)
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            self.sources = []
            for currency in ["EUR", "EUR", "EUR", "SGD", "SGD", "USD", "USD"]:
                from cost_models.models import CostModel

                model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency=currency)
                source = uuid4()
                baker.make(CostModelMap, provider_uuid=source, cost_model=model)
                self.sources.append(source)
            for month, eur in [(date(2026, 10, 1), "1.10"), (date(2026, 11, 1), "1.20")]:
                self.rate("EUR", eur, month)
                self.rate("SGD", "0.75", month)
                self.rate("GBP", "1.25", month)
            # The default report covers October; use 1.20 for its exact 245 case.
            self.rate("EUR", "1.20")

    ocp_row = CurrencyMetadataDiscovery.ocp_row
    rate = CurrencyMetadataDiscovery.rate
    handler = CurrencyMetadataDiscovery.handler
    dual_row = CurrencyMetadataDiscovery.dual_row

    def discovery_reads(self, captured):
        return [
            item["sql"]
            for item in captured
            if "reporting_" in item["sql"]
            and "daily_summary" in item["sql"]
            and item["sql"].lstrip().upper().startswith(("SELECT DISTINCT ", "WITH DISCOVERY_ROWS("))
        ]

    def test_valid_report_checks_coverage_without_discovery(self):
        """C01: report aggregation validates the actual monetary inputs."""
        from reporting.provider.ocp.models import OCPUsageLineItemDailySummary

        with tenant_context(self.tenant):
            OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=date(2026, 10, 1), usage_start__lte=date(2026, 10, 31)
            ).delete()
            self.dual_row()
            for suffix, csv, broad in [
                ("", False, False),
                ("&filter[limit]=5", False, False),
                ("&filter[offset]=0&order_by[cost]=desc", False, False),
                ("", True, False),
                ("", False, True),
            ]:
                with self.subTest(suffix=suffix, csv=csv, broad=broad):
                    handler = self.handler(suffix)
                    if broad:
                        handler.query_filter = Q(
                            usage_start__gte=date(2026, 10, 1), usage_start__lte=date(2026, 10, 31)
                        )
                    handler.is_csv_output = csv
                    with CaptureQueriesContext(connection) as captured:
                        response = handler.execute_query()
                    legacy = LegacyOCP(handler.parameters)
                    legacy.query_filter = handler.query_filter
                    legacy.is_csv_output = csv
                    self.assertEqual(response, legacy.execute_query())
                    self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))
                    self.assertEqual(self.discovery_reads(captured), [])
                    self.assertTrue(any("BOOL_OR" in q["sql"].upper() for q in captured))
                    self.assertNotIn("_currency_coverage_missing", str(response))

    def test_missing_coverage_uses_scoped_error_fallback(self):
        """C02: missing raw/model rates retain the original error details."""
        from api.currency.exceptions import ExchangeRateNotFound

        with tenant_context(self.tenant):
            self.dual_row()
            for currency, rate in [("GBP", "1.25"), ("EUR", "1.20")]:
                with self.subTest(currency=currency):
                    MonthlyExchangeRate.objects.filter(
                        base_currency=currency, effective_date=date(2026, 10, 1)
                    ).delete()
                    with CaptureQueriesContext(connection) as captured:
                        with self.assertRaises(ExchangeRateNotFound) as error:
                            self.handler().execute_query()
                    self.rate(currency, rate)
                    self.assertEqual(error.exception.status_code, 400)
                    self.assertIn(currency + " -> USD", str(error.exception.detail))
                    self.assertIn("2026-10", str(error.exception.detail))
                    self.assertNotIn("SGD", str(error.exception.detail))
                    self.assertTrue(self.discovery_reads(captured))
                    self.assertTrue(any("BOOL_OR" in q["sql"].upper() for q in captured))

    def test_unrelated_missing_model_rate_needs_no_discovery(self):
        """C03: unrelated incomplete metadata cannot add fact scans or errors."""
        with tenant_context(self.tenant):
            self.dual_row()
            MonthlyExchangeRate.objects.filter(base_currency="SGD", effective_date=date(2026, 10, 1)).delete()
            handler = self.handler()
            with CaptureQueriesContext(connection) as captured:
                response = handler.execute_query()
            self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))
            self.assertEqual(self.discovery_reads(captured), [])

    def test_coverage_includes_previous_and_undisplayed_inputs(self):
        """C04: full-period coverage survives delta and ranking scopes."""
        from api.currency.exceptions import ExchangeRateNotFound

        with tenant_context(self.tenant):
            self.rate("EUR", "1.10")
            self.dual_row(raw_currency=None, infrastructure_raw_cost=Decimal("0"))
            self.dual_row(
                raw_currency=None,
                infrastructure_raw_cost=Decimal("0"),
                usage_start=date(2026, 11, 5),
                usage_end=date(2026, 11, 5),
            )
            with self.subTest(shape="previous"):
                handler = self.handler("&delta=cost", relative=True)
                with CaptureQueriesContext(connection) as captured:
                    response = handler.execute_query()
                self.assertEqual(response["delta"]["value"], Decimal("10"))
                self.assertEqual(self.discovery_reads(captured), [])
            self.dual_row(
                source_uuid=None,
                raw_currency="JPY",
                infrastructure_raw_cost=Decimal("1"),
                cost_model_cpu_cost=Decimal("0"),
                all_labels={"product": "hidden"},
            )
            with self.subTest(shape="outside_page"):
                with CaptureQueriesContext(connection) as captured:
                    with self.assertRaises(ExchangeRateNotFound) as error:
                        self.handler("&filter[limit]=1&order_by[cost]=desc").execute_query()
                self.assertIn("JPY", str(error.exception.detail))
                self.assertTrue(any("BOOL_OR" in q["sql"].upper() for q in captured))

    def test_empty_identity_null_and_unmapped_inputs_need_no_discovery(self):
        """C05: empty/null and default-one cases remain exact and scan-free."""
        with tenant_context(self.tenant):
            cases = [
                ("standalone", self.sources[0], None, "0", "120"),
                ("identity", self.sources[5], "USD", "10", "110"),
                ("unmapped", uuid4(), "USD", "10", "110"),
            ]
            for namespace, source, raw, infra, expected in cases:
                with self.subTest(namespace=namespace):
                    self.dual_row(
                        namespace=namespace,
                        source_uuid=source,
                        raw_currency=raw,
                        infrastructure_raw_cost=Decimal(infra),
                    )
                    handler = self.handler("&filter[project]=" + namespace)
                    with CaptureQueriesContext(connection) as captured:
                        response = handler.execute_query()
                    self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
                    self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal(expected))
                    self.assertEqual(self.discovery_reads(captured), [])
            with self.subTest(namespace="empty"):
                handler = self.handler("&filter[project]=absent")
                with CaptureQueriesContext(connection) as captured:
                    response = handler.execute_query()
                self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
                self.assertEqual(self.discovery_reads(captured), [])

    def test_coverage_fast_path_eligibility_and_scope(self):
        """C06: other schemas and denied currencies cannot influence coverage."""
        from cost_models.models import CostModel

        other = Tenant.objects.get(schema_name="org2222222")
        with tenant_context(other):
            model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency="JPY")
            baker.make(CostModelMap, provider_uuid=self.sources[0], cost_model=model)
            self.dual_row(raw_currency="JPY", infrastructure_raw_cost=Decimal("999"))
        with tenant_context(self.tenant):
            self.dual_row()
            self.dual_row(namespace="denied", source_uuid=uuid4(), raw_currency="JPY")
            handler = self.handler("&exclude[project]=denied")
            with CaptureQueriesContext(connection) as captured:
                response = handler.execute_query()
            self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))
            self.assertEqual(self.discovery_reads(captured), [])

    def test_aggregation_uses_one_rate_snapshot(self):
        """C07: eligibility, annotations and fallback share loaded metadata."""
        with tenant_context(self.tenant):
            self.dual_row()
            handler = self.handler()
            with CaptureQueriesContext(connection) as initial:
                handler.request_source_to_currency_map
                handler.monthly_exchange_rate_map
            self.assertEqual(sum("monthly_exchange_rate" in q["sql"].lower() for q in initial), 1)
            MonthlyExchangeRate.objects.filter(base_currency="EUR", effective_date=date(2026, 10, 1)).update(
                exchange_rate=Decimal("9")
            )
            MonthlyExchangeRate.objects.filter(base_currency="SGD").delete()
            with CaptureQueriesContext(connection) as captured:
                response = handler.execute_query()
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))
            self.assertEqual(self.handler().execute_query()["total"]["cost"]["total"]["value"], Decimal("1025"))
            self.assertFalse(any("monthly_exchange_rate" in q["sql"].lower() for q in captured))
            self.assertEqual(self.discovery_reads(initial), [])

    def test_zero_amount_inputs_still_require_currency_coverage(self):
        """Coverage follows actual input identities, including zero-valued rows."""
        from api.currency.exceptions import ExchangeRateNotFound

        with tenant_context(self.tenant):
            self.dual_row(infrastructure_raw_cost=Decimal("0"), cost_model_cpu_cost=Decimal("0"))
            for currency, value in [("GBP", "1.25"), ("EUR", "1.20")]:
                with self.subTest(currency=currency):
                    MonthlyExchangeRate.objects.filter(base_currency=currency).delete()
                    with self.assertRaises(ExchangeRateNotFound) as error:
                        self.handler().execute_query()
                    self.assertEqual(error.exception.status_code, 400)
                    self.assertIn(currency + " -> USD", str(error.exception.detail))
                    self.rate(currency, value)

    def test_inconsistent_coverage_result_fails_closed(self):
        """Discard inconsistent provisional totals if scoped validation disagrees."""
        with tenant_context(self.tenant):
            self.dual_row()
            totals = {"_currency_coverage_missing": True}
            with self.assertRaisesRegex(RuntimeError, "Coverage aggregate disagrees with scoped currency validation"):
                self.handler()._validate_currency_coverage(totals)
            self.assertEqual(totals, {})

    def test_large_snapshot_bounds_conversion_expression(self):
        """Use metadata lookup instead of an unbounded per-currency CASE."""
        from api.currency.currencies import get_active_iso_currency_codes

        with tenant_context(self.tenant):
            self.dual_row()
            for code in sorted(get_active_iso_currency_codes() - {"USD", "EUR", "GBP", "SGD"})[:40]:
                self.rate(code, "1.23456789")
            handler = self.handler()
            with CaptureQueriesContext(connection) as captured:
                response = handler.execute_query()
            self.assertEqual(response, LegacyOCP(handler.parameters).execute_query())
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))
            self.assertEqual(self.discovery_reads(captured), [])
            totals = [item["sql"] for item in captured if "BOOL_OR" in item["sql"].upper()]
            self.assertTrue(totals)
            self.assertTrue(all("->>" in statement for statement in totals))

    def test_unsupported_shapes_keep_scoped_discovery(self):
        """C06: summaries, org units and other providers retain the discovery route."""
        variants = [
            (AzureReportQueryHandler, AzureCostView, "", "azure"),
            (GCPReportQueryHandler, GCPCostView, "", "gcp"),
            (OCPReportQueryHandler, OCPCostView, "", "openshift"),
            (AWSReportQueryHandler, AWSCostView, "&group_by[org_unit_id]=OU_001", "aws"),
        ]
        with tenant_context(self.tenant):
            for cls, view, suffix, provider in variants:
                with self.subTest(provider=cls.__name__, suffix=suffix):
                    params = self.mocked_query_params(
                        "?start_date=2026-10-01&end_date=2026-10-31" + suffix,
                        view,
                        path=f"/api/cost-management/v1/reports/{provider}/costs/",
                    )
                    handler = cls(params)
                    if cls is OCPReportQueryHandler:
                        self.assertIsNot(handler.query_table, handler._mapper.query_table)
                    if cls is AWSReportQueryHandler:
                        self.assertTrue(handler._org_unit_requested)
                    self.assertFalse(handler.aggregate_currency_coverage_enabled)
                    with CaptureQueriesContext(connection) as captured:
                        handler.monthly_exchange_rate_map
                    table = handler.query_table._meta.db_table
                    self.assertTrue(
                        any(
                            table in item["sql"]
                            and item["sql"].lstrip().upper().startswith(("SELECT DISTINCT ", "WITH DISCOVERY_ROWS("))
                            for item in captured
                        )
                    )
                    self.assertFalse(any("BOOL_OR" in item["sql"].upper() for item in captured))

    def test_summary_path_preserves_complete_and_incomplete_metadata(self):
        """C06: compatibility path retains money, gap fallback and empty scopes."""
        from reporting.provider.models import TenantAPIProvider

        with tenant_context(self.tenant):
            params = self.mocked_query_params(
                "?start_date=2026-10-01&end_date=2026-10-31&filter[cluster]=cc8584-compatibility",
                OCPCostView,
                path="/api/cost-management/v1/reports/openshift/costs/",
            )
            source = baker.make(TenantAPIProvider, uuid=self.sources[0], type=Provider.PROVIDER_OCP)
            initial = OCPReportQueryHandler(params)
            self.assertIsNot(initial.query_table, initial._mapper.query_table)
            baker.make(
                initial.query_table,
                cluster_id="cc8584-compatibility",
                cluster_alias="cc8584-compatibility",
                infrastructure_markup_cost=Decimal("0"),
                distributed_cost=Decimal("0"),
                cost_model_memory_cost=Decimal("0"),
                cost_model_volume_cost=Decimal("0"),
                cost_model_gpu_cost=Decimal("0"),
                infrastructure_usage_cost={},
                infrastructure_monthly_cost_json={},
                supplementary_usage_cost={},
                supplementary_monthly_cost_json={},
                source_uuid=source,
                raw_currency="GBP",
                usage_start=date(2026, 10, 5),
                usage_end=date(2026, 10, 5),
                infrastructure_raw_cost=Decimal("100"),
                cost_model_cpu_cost=Decimal("100"),
                cost_model_rate_type="Supplementary",
            )
            for profile, expected in [("complete", "245"), ("unrelated-gap", "245"), ("unmapped", "225")]:
                with self.subTest(profile=profile):
                    if profile == "unrelated-gap":
                        MonthlyExchangeRate.objects.filter(base_currency="SGD").delete()
                    if profile == "unmapped":
                        CostModelMap.objects.all().delete()
                    handler = OCPReportQueryHandler(params)
                    self.assertFalse(handler.aggregate_currency_coverage_enabled)
                    with CaptureQueriesContext(connection) as captured:
                        response = handler.execute_query()
                    self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal(expected))
                    self.assertEqual(response, LegacyOCP(params).execute_query())
                    self.assertFalse(any("BOOL_OR" in item["sql"].upper() for item in captured))
                    if profile == "unrelated-gap":
                        self.assertNotIn("SGD", handler.monthly_exchange_rate_map)
                        self.assertEqual(set(handler.request_source_to_currency_map.values()), {"EUR"})
            empty = OCPReportQueryHandler(params)
            legacy = LegacyOCP(params)
            empty.query_filter = legacy.query_filter = Q(pk__in=[])
            with CaptureQueriesContext(connection) as captured:
                response = empty.execute_query()
                self.assertEqual(empty.raw_currencies_for_conversion, set())
            self.assertEqual(response, legacy.execute_query())
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("0"))
            self.assertFalse(any(empty.query_table._meta.db_table in item["sql"] for item in captured))

    def test_large_snapshot_preserves_nondefault_target_and_identity(self):
        """Large lookups use the requested target rather than assuming USD."""
        from api.currency.currencies import get_active_iso_currency_codes

        with tenant_context(self.tenant):
            for code in sorted(get_active_iso_currency_codes() - {"USD", "EUR", "GBP", "SGD"})[:40]:
                MonthlyExchangeRate.objects.create(
                    base_currency=code,
                    target_currency="EUR",
                    effective_date=date(2026, 10, 1),
                    exchange_rate=Decimal("1.23456789"),
                    rate_type="static",
                )
            MonthlyExchangeRate.objects.create(
                base_currency="USD",
                target_currency="EUR",
                effective_date=date(2026, 10, 1),
                exchange_rate=Decimal("0.9"),
                rate_type="static",
            )
            self.dual_row(raw_currency="USD")
            self.dual_row(raw_currency="EUR")
            handler = self.handler("&currency=EUR")
            handler.is_csv_output = True
            with CaptureQueriesContext(connection) as captured:
                response = handler.execute_query()
            legacy = LegacyOCP(handler.parameters)
            legacy.is_csv_output = True
            self.assertEqual(response, legacy.execute_query())
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("390"))
            self.assertEqual(response["currency"], "EUR")
            self.assertEqual(self.discovery_reads(captured), [])
            self.assertTrue(any("->>" in item["sql"] for item in captured))


class CurrencyCoverageConcurrencyTest(SimpleTestCase):
    """C08: actual committed writes between report statements on another connection."""

    databases = {"default"}
    aws_row = fixtures.CurrencyDiscoveryTest.aws_row

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connection.set_schema_to_public()
        cls.tenant = Tenant.objects.create(schema_name="org8584" + str(uuid4().int % 10**12))
        cls.addClassCleanup(cls.remove_tenant)
        cls.tenant.create_schema()

    @classmethod
    def remove_tenant(cls):
        connection.set_schema_to_public()
        cls.tenant.delete(force_drop=True)

    def setUp(self):
        from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary

        super().setUp()
        self.enterContext(patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True))
        self.enterContext(patch("api.report.queries.is_currency_discovery_optimization_enabled", return_value=True))
        self.enterContext(patch("api.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=timezone.utc)))
        with tenant_context(self.tenant):
            AWSCostEntryLineItemDailySummary.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            AWSEnabledCategoryKeys.objects.update_or_create(key="CostCenter", defaults={"enabled": True})
            self.row = self.aws_row()

    def handler(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from django.test import RequestFactory
        from api.query_params import QueryParameters

        request = RequestFactory().get(
            "?start_date=2026-10-01&end_date=2026-10-31&group_by[account]=*" "&filter[aws_category:CostCenter]=cc8584"
        )
        request.path = "/api/cost-management/v1/reports/aws/costs/"
        request.user = Mock(access={}, customer=SimpleNamespace(schema_name=self.tenant.schema_name))
        return AWSReportQueryHandler(QueryParameters(request, AWSCostView))

    def insert_uncovered_row(self):
        from contextlib import closing
        import psycopg2
        from psycopg2 import sql

        model = type(self.row)
        fields = [
            field
            for field in model._meta.concrete_fields
            if not getattr(field, "generated", False)
            and field.get_internal_type() not in {"AutoField", "BigAutoField", "SmallAutoField"}
        ]
        replacements = {"uuid": uuid4(), "currency_code": "GBP"}
        parameters = []
        expressions = []
        for field in fields:
            if field.column in replacements:
                expressions.append(sql.Placeholder())
                parameters.append(replacements[field.column])
            else:
                expressions.append(sql.Identifier("original", field.column))
        parameters.append(self.row.uuid)
        table = sql.Identifier(self.tenant.schema_name, model._meta.db_table)
        statement = sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {} original WHERE original.uuid=%s").format(
            table,
            sql.SQL(",").join(sql.Identifier(field.column) for field in fields),
            sql.SQL(",").join(expressions),
            table,
        )
        with closing(psycopg2.connect(**connection.get_connection_params())) as writer:
            writer.autocommit = True
            with writer.cursor() as cursor:
                cursor.execute(sql.SQL("SET search_path TO {},public").format(sql.Identifier(self.tenant.schema_name)))
                cursor.execute(statement, parameters)
                self.assertEqual(cursor.rowcount, 1)

    def test_concurrent_input_change_cannot_return_unvalidated_money(self):
        from api.currency.exceptions import ExchangeRateNotFound

        inserted = False

        def write_after_totals(execute, statement, params, many, context):
            nonlocal inserted
            result = execute(statement, params, many, context)
            if not inserted and "_currency_coverage_missing" in statement and "SUM(" in statement.upper():
                self.insert_uncovered_row()
                inserted = True
            return result

        with tenant_context(self.tenant):
            handler = self.handler()
            expected = LegacyAWS(handler.parameters).execute_query()
            with connection.execute_wrapper(write_after_totals):
                response = handler.execute_query()
            self.assertTrue(inserted, "The concurrent committed write must actually execute")
            self.assertEqual(response, expected)
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("100"))
            with self.assertRaises(ExchangeRateNotFound) as error:
                self.handler().execute_query()
            self.assertIn("GBP -> USD", str(error.exception.detail))

    def test_incompatible_parent_transaction_retains_discovery(self):
        from django.db import transaction

        with tenant_context(self.tenant), transaction.atomic():
            handler = self.handler()
            with CaptureQueriesContext(connection) as captured:
                response = handler.execute_query()
            self.assertFalse(handler.aggregate_currency_coverage_enabled)
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("100"))
            self.assertTrue(any("DISCOVERY_ROWS" in item["sql"].upper() for item in captured))

    def test_primed_handler_rejects_incompatible_parent_transaction(self):
        """C08: cached eligibility cannot bypass the actual transaction boundary."""
        from django.db import transaction

        with tenant_context(self.tenant):
            handler = self.handler()
            self.assertTrue(handler.aggregate_currency_coverage_enabled)
            handler.monthly_exchange_rate_map
            with transaction.atomic():
                with self.assertRaisesRegex(
                    transaction.TransactionManagementError, "consistent currency coverage snapshot"
                ):
                    handler.execute_query()
