#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database contracts for scoped currency discovery (COST-8584)."""
from datetime import date
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.db import connections
from django.db.models import Q
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import tenant_context
from model_bakery import baker

from api.currency.exceptions import ExchangeRateNotFound
from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.view import AWSCostView
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import MonthlyExchangeRate
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSEnabledCategoryKeys
from reporting.provider.models import TenantAPIProvider
from reporting.provider.ocp.models import OCPCostSummaryP
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


class CurrencySnapshotTestCase(IamTestCase):
    """Use a real repeatable-read snapshot for conversion report tests."""

    @classmethod
    def _enter_atomics(cls):
        outer = [alias for alias in cls._databases_names() if not connections[alias].in_atomic_block]
        atomics = super()._enter_atomics()
        for alias in outer:
            with connections[alias].cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return atomics


class CurrencyDiscoveryTest(CurrencySnapshotTestCase):
    """Use real scoped ORM discovery; do not mock the method under test."""

    def setUp(self):
        super().setUp()
        with tenant_context(self.tenant):
            EnabledTagKeys.objects.get_or_create(key="product", provider_type=Provider.PROVIDER_OCP)
            AWSEnabledCategoryKeys.objects.update_or_create(key="CostCenter", defaults={"enabled": True})

    def ocp_row(self, **values):
        fields = {
            "uuid": uuid4(),
            "usage_start": date(2026, 10, 5),
            "usage_end": date(2026, 10, 5),
            "cluster_id": "cc-alpha",
            "cluster_alias": "cc-alpha",
            "namespace": "cc-project",
            "source_uuid": uuid4(),
            "raw_currency": "USD",
            "all_labels": {"product": "rhel"},
            "infrastructure_raw_cost": Decimal("100"),
            "data_source": "Pod",
        }
        fields.update(values)
        return baker.make(OCPUsageLineItemDailySummary, **fields)

    def ocp_handler(self):
        params = self.mocked_query_params(
            "?start_date=2026-10-01&end_date=2026-10-31&filter[cluster]=cc-alpha&group_by[tag:product]=*",
            OCPCostView,
            path="/api/cost-management/v1/reports/openshift/costs/",
        )
        return OCPReportQueryHandler(params)

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.queries.is_currency_discovery_optimization_enabled", return_value=True)
    def test_empty_cost_model_map_avoids_source_scan(self, _discovery, _flags):
        """S03: no model mappings require no raw source enumeration."""
        with tenant_context(self.tenant):
            CostModelMap.objects.all().delete()
            self.ocp_row()
            handler = self.ocp_handler()
            with CaptureQueriesContext(connection) as captured:
                result = handler.request_source_to_currency_map
            self.assertEqual(result, {})
            raw_reads = [q["sql"] for q in captured if 'FROM "reporting_ocpusagelineitem_daily_summary"' in q["sql"]]
            self.assertEqual(raw_reads, [], "Empty mappings must not enumerate raw source UUIDs")

    @patch("api.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=timezone.utc))
    def test_filters_access_and_exclusions_bound_discovery(self, _clock):
        """S05: excluded previous-period rows must not add required currencies."""
        with tenant_context(self.tenant):
            for day, account, currency in [
                (date(2026, 11, 5), "111111111111", "USD"),
                (date(2026, 10, 5), "111111111111", "EUR"),
                (date(2026, 10, 5), "222222222222", "JPY"),
            ]:
                baker.make(
                    AWSCostEntryLineItemDailySummary,
                    uuid=uuid4(),
                    usage_start=day,
                    usage_end=day,
                    usage_account_id=account,
                    currency_code=currency,
                    cost_category={"CostCenter": "cc8584"},
                    unblended_cost=Decimal("100"),
                )
            params = self.mocked_query_params(
                "?delta=cost&filter[resolution]=daily&"
                "filter[time_scope_units]=month&filter[time_scope_value]=-1&"
                "filter[aws_category:CostCenter]=cc8584&exclude[account]=222222222222",
                AWSCostView,
                path="/api/cost-management/v1/reports/aws/costs/",
            )
            handler = AWSReportQueryHandler(params)
            self.assertEqual(set(handler.conversion_queryset.values_list("currency_code", flat=True)), {"USD"})
            previous = set(handler.previous_conversion_queryset.values_list("currency_code", flat=True))
            self.assertEqual(previous, {"EUR"}, "Excluded previous-period account must not require JPY conversion")
            self.assertEqual(handler.raw_currencies_for_conversion, {"USD", "EUR"})

    def aws_handler(self, query):
        return AWSReportQueryHandler(
            self.mocked_query_params("?" + query, AWSCostView, path="/api/cost-management/v1/reports/aws/costs/")
        )

    def aws_row(self, currency="USD", day=date(2026, 10, 5), **values):
        fields = dict(
            uuid=uuid4(),
            usage_start=day,
            usage_end=day,
            usage_account_id="111111111111",
            currency_code=currency,
            cost_category={"CostCenter": "cc8584"},
            unblended_cost=Decimal("100"),
            markup_cost=Decimal("0"),
        )
        fields.update(values)
        return baker.make(AWSCostEntryLineItemDailySummary, **fields)

    def rate(self, base, value, month=date(2026, 10, 1)):
        MonthlyExchangeRate.objects.update_or_create(
            base_currency=base,
            target_currency="USD",
            effective_date=month,
            defaults={"exchange_rate": Decimal(value), "rate_type": "static"},
        )

    def test_ocp_tag_grouping_preserves_discovery_membership(self):
        """S01: grouping keeps exact raw source and currency membership."""
        with tenant_context(self.tenant):
            first = self.ocp_row(raw_currency="USD")
            second = self.ocp_row(raw_currency="EUR")
            self.ocp_row(raw_currency="JPY", cluster_id="cc-beta", cluster_alias="cc-beta")
            handler = self.ocp_handler()
            self.assertEqual(handler.source_uuids_for_conversion, {first.source_uuid, second.source_uuid})
            self.assertEqual(handler.raw_currencies_for_conversion, {"USD", "EUR"})

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.queries.is_currency_discovery_optimization_enabled", return_value=True)
    def test_unmapped_source_does_not_require_other_models_rates(self, _discovery, _ocp_flag, _base_flag):
        """S02: unrelated non-USD models do not require exchange rates."""
        with tenant_context(self.tenant):
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            row = self.ocp_row()
            for currency in ["EUR", "SGD"]:
                model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency=currency)
                baker.make(CostModelMap, cost_model=model, provider_uuid=uuid4())
            handler = self.ocp_handler()
            self.assertNotIn(row.source_uuid, handler.request_source_to_currency_map)
            self.assertEqual(set(handler.request_source_to_currency_map.values()), {"EUR", "SGD"})
            response = handler.execute_query()
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("100"))

    @patch("api.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=timezone.utc))
    def test_aws_previous_period_currency_is_discovered(self, _clock):
        """S04: a currency present only in the previous period is included."""
        with tenant_context(self.tenant):
            self.aws_row("USD", date(2026, 11, 5))
            self.aws_row("EUR", date(2026, 10, 5))
            self.aws_row("JPY", date(2026, 9, 5))
            handler = self.aws_handler(
                "delta=cost&filter[resolution]=daily&filter[time_scope_units]=month&"
                "filter[time_scope_value]=-1&filter[aws_category:CostCenter]=cc8584"
            )
            self.assertEqual(handler.raw_currencies_for_conversion, {"USD", "EUR"})

    def test_substring_category_and_cluster_semantics_are_preserved(self):
        """S06: existing substring predicates must not become equality predicates."""
        with tenant_context(self.tenant):
            first = self.ocp_row(raw_currency="USD")
            second = self.ocp_row(raw_currency="EUR", cluster_id="cc-alpha-2", cluster_alias="cc-alpha-2")
            self.ocp_row(raw_currency="JPY", cluster_id="cc-beta", cluster_alias="cc-beta")
            self.assertEqual(self.ocp_handler().source_uuids_for_conversion, {first.source_uuid, second.source_uuid})
            for code, currency in [("106", "USD"), ("1106", "EUR"), ("206", "JPY")]:
                self.aws_row(currency, cost_category={"CostCenter": code})
            handler = self.aws_handler(
                "start_date=2026-10-01&end_date=2026-10-31&" "filter[aws_category:CostCenter]=106"
            )
            self.assertEqual(handler.raw_currencies_for_conversion, {"USD", "EUR"})

    def test_missing_or_stale_summary_cannot_change_discovery(self):
        """S07: summary ghosts and missing raw membership remain irrelevant."""
        with tenant_context(self.tenant):
            row = self.ocp_row(raw_currency="EUR")
            ghost = baker.make(TenantAPIProvider, name="cc8584-ghost", type=Provider.PROVIDER_OCP)
            baker.make(
                OCPCostSummaryP,
                id=uuid4(),
                source_uuid=ghost,
                raw_currency="JPY",
                usage_start=date(2026, 10, 5),
                usage_end=date(2026, 10, 5),
                cluster_id="cc-alpha",
                cluster_alias="cc-alpha",
            )
            handler = self.ocp_handler()
            self.assertEqual(handler.source_uuids_for_conversion, {row.source_uuid})
            self.assertEqual(handler.raw_currencies_for_conversion, {"EUR"})

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True)
    def test_monthly_dual_currency_conversion_uses_exact_rates(self, _ocp_flag, _base_flag):
        """S08: independent infrastructure and model currencies retain exact values."""
        with tenant_context(self.tenant):
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            row = self.ocp_row(
                raw_currency="GBP", cost_model_cpu_cost=Decimal("100"), cost_model_rate_type="Supplementary"
            )
            model = baker.make(CostModel, source_type=Provider.PROVIDER_OCP, currency="EUR")
            baker.make(CostModelMap, cost_model=model, provider_uuid=row.source_uuid)
            self.rate("GBP", "1.25")
            self.rate("EUR", "1.20")
            response = self.ocp_handler().execute_query()
            self.assertEqual(response["total"]["infrastructure"]["total"]["value"], Decimal("125"))
            self.assertEqual(response["total"]["supplementary"]["total"]["value"], Decimal("120"))
            self.assertEqual(response["total"]["cost"]["total"]["value"], Decimal("245"))

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.ocp.query_handler.is_feature_flag_enabled_by_schema", return_value=True)
    def test_missing_rate_and_month_coverage_contract_is_preserved(self, _ocp_flag, _base_flag):
        """S09: do not narrow the existing requested currency by month coverage."""
        with tenant_context(self.tenant):
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            self.ocp_row(raw_currency="EUR", usage_start=date(2026, 11, 5), usage_end=date(2026, 11, 5))
            self.ocp_row(raw_currency="JPY", cluster_id="cc-beta", cluster_alias="cc-beta")
            self.rate("EUR", "1.20", date(2026, 11, 1))
            params = self.mocked_query_params(
                "?start_date=2026-10-01&end_date=2026-11-09&filter[cluster]=cc-alpha&group_by[tag:product]=*",
                OCPCostView,
                path="/api/cost-management/v1/reports/openshift/costs/",
            )
            with self.assertRaises(ExchangeRateNotFound) as raised:
                OCPReportQueryHandler(params).execute_query()
            self.assertEqual(raised.exception.status_code, 400)
            detail = str(raised.exception.detail["currency"])
            self.assertIn("EUR -> USD", detail)
            self.assertIn("2026-10", detail)
            self.assertNotIn("JPY", detail)

    def test_identity_null_and_empty_inputs_keep_existing_behavior(self):
        """S10: identity needs no monthly row; null and empty sets remain empty."""
        with tenant_context(self.tenant):
            CostModelMap.objects.all().delete()
            MonthlyExchangeRate.objects.all().delete()
            self.ocp_row(source_uuid=None, raw_currency=None)
            handler = self.ocp_handler()
            self.assertEqual(handler.source_uuids_for_conversion, set())
            self.assertEqual(handler.raw_currencies_for_conversion, set())
            self.assertEqual(handler.monthly_exchange_rate_map, {})
            self.ocp_row(source_uuid=None, raw_currency="USD")
            handler = self.ocp_handler()
            self.assertEqual(handler.monthly_exchange_rate_map, {"USD": {date(2026, 10, 1): Decimal("1")}})
            params = self.mocked_query_params(
                "?start_date=2026-10-01&end_date=2026-10-31&filter[cluster]=cc-absent&group_by[tag:product]=*",
                OCPCostView,
                path="/api/cost-management/v1/reports/openshift/costs/",
            )
            self.assertEqual(OCPReportQueryHandler(params).raw_currencies_for_conversion, set())

    @patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=True)
    @patch("api.report.queries.is_currency_discovery_optimization_enabled", return_value=True)
    def test_date_only_discovery_retains_distinct_shape(self, _rollout, _constant):
        """S01/S10: broad OCP discovery keeps parallel-friendly aggregation."""
        with tenant_context(self.tenant):
            for currency in ["USD", "EUR", "GBP", None]:
                self.ocp_row(raw_currency=currency)
            handler = OCPReportQueryHandler(
                self.mocked_query_params(
                    "?start_date=2026-10-01&end_date=2026-10-31&group_by[tag:product]=*", OCPCostView
                )
            )
            expected = set(
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=date(2026, 10, 1), usage_start__lte=date(2026, 10, 31)
                ).values_list("raw_currency", flat=True)
            ) - {None}
            with CaptureQueriesContext(connection) as captured:
                actual = handler.raw_currencies_for_conversion
            self.assertEqual(actual, expected)
            self.assertTrue({"USD", "EUR", "GBP"}.issubset(actual))
            reads = [q["sql"] for q in captured if "reporting_ocpusagelineitem_daily_summary" in q["sql"]]
            self.assertEqual(len(reads), 1)
            self.assertTrue(reads[0].lstrip().upper().startswith("SELECT DISTINCT "), reads[0])

    def test_empty_access_scope_discovers_nothing(self):
        """S05/S10: an ORM-elided denied scope returns no identities."""
        with tenant_context(self.tenant):
            self.ocp_row()
            handler = self.ocp_handler()
            handler.query_filter = Q(pk__in=[])
            self.assertEqual(handler.raw_currencies_for_conversion, set())
            self.assertEqual(handler.source_uuids_for_conversion, set())

    def test_filter_values_remain_bound_parameters(self):
        """S05/S06: punctuation in caller filters remains literal data."""
        with tenant_context(self.tenant):
            token = "cc-'%; SELECT 8584 --"
            row = self.ocp_row(cluster_id=token, cluster_alias=token, raw_currency="EUR")
            self.ocp_row(raw_currency="JPY")
            handler = OCPReportQueryHandler(
                self.mocked_query_params(
                    "?start_date=2026-10-01&end_date=2026-10-31&group_by[tag:product]=*", OCPCostView
                )
            )
            handler.query_filter &= Q(cluster_id=token)
            self.assertEqual(handler.raw_currencies_for_conversion, {"EUR"})
            self.assertEqual(handler.source_uuids_for_conversion, {row.source_uuid})
