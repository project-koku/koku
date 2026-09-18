#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Regression coverage for the flagged OCP distributed-cost delta aggregate."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import PropertyMock

from django.db.models import DecimalField
from django.db.models import Value
from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.report.ocp.provider_map import OCPProviderMap
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.queries import ReportQueryHandler
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


COMBINED_DISTRIBUTED_COST_FLAG = "cost-management.backend.ocp_report_combined_distributed_cost"
FLAG_TARGET = "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema"


class OCPCombinedDistributedCostTest(IamTestCase):
    """The one-SUM delta experiment must preserve OCP distributed-cost values."""

    url = (
        "?delta=distributed_cost&group_by[project]=*&filter[resolution]=monthly"
        "&filter[time_scope_value]=-1&filter[time_scope_units]=month"
        "&filter[limit]=10&filter[offset]=0&order_by[distributed_cost]=desc"
    )

    @staticmethod
    def _feature_flag(_schema, feature_flag, **_kwargs):
        return feature_flag == COMBINED_DISTRIBUTED_COST_FLAG

    def _handler(self, url=None, view=OCPCostView, path="/api/cost-management/v1/reports/openshift/costs/"):
        params = self.mocked_query_params(
            url or self.url,
            view,
            path=path,
        )
        return OCPReportQueryHandler(params)

    def test_combined_aggregate_matches_legacy_for_rates_and_nulls(self):
        """One SUM retains every distributed rate type and NULL-as-zero behavior."""
        rows = (
            ("platform_distributed", 11, 4, 1, 2, None, 1, None),
            ("worker_distributed", 5, None, 2, 0, 3, None, 1),
            ("unattributed_storage", 7, 2, None, 0, 4, None, None),
            ("unattributed_network", 13, 1, 1, None, None, None, 2),
            ("gpu_distributed", 3, 0, 0, 1, None, None, None),
            ("unrecognized", 999, 1, 1, 1, None, None, None),
        )
        decimal = DecimalField(max_digits=33, decimal_places=15)

        with tenant_context(self.tenant):
            OCPUsageLineItemDailySummary.objects.all().delete()
            for rate_type, distributed, raw, markup, cpu, memory, volume, gpu in rows:
                self.baker.make(
                    OCPUsageLineItemDailySummary,
                    cost_model_rate_type=rate_type,
                    distributed_cost=Decimal(distributed),
                    infrastructure_raw_cost=None if raw is None else Decimal(raw),
                    infrastructure_markup_cost=None if markup is None else Decimal(markup),
                    cost_model_cpu_cost=None if cpu is None else Decimal(cpu),
                    cost_model_memory_cost=None if memory is None else Decimal(memory),
                    cost_model_volume_cost=None if volume is None else Decimal(volume),
                    cost_model_gpu_cost=None if gpu is None else Decimal(gpu),
                )

            mapper = OCPProviderMap(Provider.PROVIDER_OCP, "costs_by_project", self.schema_name)
            legacy = mapper.report_type_map["delta_key"]["cost_total_distributed"]
            query = OCPUsageLineItemDailySummary.objects.annotate(
                exchange_rate=Value(Decimal("2"), output_field=decimal),
                infra_exchange_rate=Value(Decimal("3"), output_field=decimal),
            )

            totals = query.aggregate(legacy=legacy, combined=mapper.combined_distributed_cost)
            combined_sql = str(query.values("usage_start").annotate(cost=mapper.combined_distributed_cost).query)

        self.assertEqual(Decimal("167"), totals["legacy"])
        self.assertEqual(totals["legacy"], totals["combined"])
        self.assertEqual(1, combined_sql.upper().count("SUM("))

    def test_eligible_schema_flag_selects_combined_delta_aggregate(self):
        """Only the scoped schema flag selects the single-aggregate delta expression."""
        seen = []

        def feature_flag(schema, feature_flag, **kwargs):
            seen.append((schema, feature_flag, kwargs.get("dev_fallback")))
            return self._feature_flag(schema, feature_flag, **kwargs)

        with patch(FLAG_TARGET, side_effect=feature_flag):
            handler = self._handler()
            self.assertTrue(handler._combined_distributed_cost_for_limited_delta_enabled)
            self.assertIs(handler._get_delta_field(), handler._mapper.combined_distributed_cost)

        self.assertIn((self.schema_name, COMBINED_DISTRIBUTED_COST_FLAG, True), seen)

    def test_enabled_flag_preserves_complete_delta_response(self):
        """The new aggregate is exactly response-compatible with the legacy path."""
        with patch(FLAG_TARGET, return_value=False):
            legacy = self._handler().execute_query()

        handler = self._handler()
        selected_delta_fields = []
        get_delta_field = handler._get_delta_field

        def capture_delta_field():
            delta_field = get_delta_field()
            selected_delta_fields.append(delta_field)
            return delta_field

        with patch(FLAG_TARGET, side_effect=self._feature_flag):
            with patch.object(handler, "_get_delta_field", side_effect=capture_delta_field):
                optimized = handler.execute_query()

        self.assertEqual(legacy, optimized)
        self.assertTrue(
            any(delta_field is handler._mapper.combined_distributed_cost for delta_field in selected_delta_fields)
        )

    def test_disabled_flag_keeps_legacy_delta_aggregate(self):
        """An eligible request remains on the legacy aggregate until explicitly enabled."""
        with patch(FLAG_TARGET, return_value=False):
            handler = self._handler()
            self.assertFalse(handler._combined_distributed_cost_for_limited_delta_enabled)
            self.assertIs(
                handler._get_delta_field(),
                handler._mapper.report_type_map["delta_key"]["cost_total_distributed"],
            )

    def test_ineligible_requests_keep_legacy_delta_aggregate(self):
        """The flag cannot broaden from the bounded Banco report shape."""
        ineligible_urls = (
            self.url.replace("&filter[offset]=0", ""),
            self.url.replace("filter[resolution]=monthly", "filter[resolution]=daily"),
            self.url.replace("&order_by", "&group_by[cluster]=*&order_by"),
        )

        with patch(FLAG_TARGET, side_effect=self._feature_flag):
            for url in ineligible_urls:
                with self.subTest(url=url):
                    handler = self._handler(url)
                    self.assertFalse(handler._combined_distributed_cost_for_limited_delta_enabled)
                    self.assertIs(
                        handler._get_delta_field(),
                        handler._mapper.report_type_map["delta_key"]["cost_total_distributed"],
                    )

            cpu_url = self.url.replace("?delta=distributed_cost&", "?")
            cpu_handler = self._handler(
                cpu_url,
                view=OCPCpuView,
                path="/api/cost-management/v1/reports/openshift/cpu/",
            )
            self.assertFalse(cpu_handler._combined_distributed_cost_for_limited_delta_enabled)

            with patch("reporting.provider.ocp.models.OpenshiftCostCategory.objects") as categories:
                categories.values_list.return_value.distinct.return_value = ["Platform"]
                category_handler = self._handler(self.url.replace("&order_by", "&category=*&order_by"))
            self.assertFalse(category_handler._combined_distributed_cost_for_limited_delta_enabled)

            with patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock) as accept_type:
                accept_type.return_value = "text/csv"
                csv_handler = self._handler()
            self.assertFalse(csv_handler._combined_distributed_cost_for_limited_delta_enabled)

    def test_base_delta_field_hook_keeps_the_provider_expression(self):
        """Providers without an override retain their existing delta mapping."""
        handler = object.__new__(ReportQueryHandler)
        expected = object()
        handler._delta = "cost_total"
        handler._mapper = SimpleNamespace(_report_type_map={"delta_key": {"cost_total": expected}})

        self.assertIs(expected, handler._get_delta_field())
