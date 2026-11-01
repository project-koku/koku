#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for OCP CSV base_currency / exchange_rate audit column fallbacks."""
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db.models import Case
from django.db.models import DecimalField
from django.db.models import Max
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Coalesce
from django_tenants.utils import tenant_context

from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from masu.test import MasuTestCase

FLAG_TARGET = "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema"
OCP_PATH = "/api/cost-management/v1/reports/openshift/costs/"


class OCPCsvCurrencyAuditTest(MasuTestCase):
    """Verify CSV audit annotations prefer infra values, else cost-model values."""

    def _handler(self):
        # Avoid ?currency=... — serializer validates against EnabledCurrency.
        query_params = self.mocked_query_params("?", OCPCostView, path=OCP_PATH)
        handler = OCPReportQueryHandler(query_params)
        handler.is_csv_output = True
        handler.currency = "USD"
        source_uuid = self.ocp_provider.uuid
        handler.__dict__["source_to_currency_map"] = {source_uuid: "SEK"}
        handler.__dict__["request_source_to_currency_map"] = {source_uuid: "SEK"}
        handler.__dict__["raw_currencies_for_conversion"] = set()
        handler.__dict__["monthly_exchange_rate_map"] = {
            "SEK": {handler.start_datetime.date().replace(day=1): Decimal("0.095")},
        }
        handler.__dict__["exchange_rates"] = {
            "SEK": {"USD": Decimal("0.095")},
            "EUR": {"USD": Decimal("1.1")},
        }
        return handler, source_uuid

    def _infra_case(self, rate_by_currency):
        """Controlled infra exchange-rate Case used when the constant-currency flag is off."""
        return Case(
            *[When(raw_currency=currency, then=Value(rate)) for currency, rate in rate_by_currency.items()],
            default=1,
            output_field=DecimalField(),
        )

    def _aggregate_csv_row(self, handler, row_id, *, constant_currency, infra_rates=None):
        flag_patch = patch(FLAG_TARGET, return_value=constant_currency)
        infra_patch = patch(
            "api.report.ocp.query_handler.build_exchange_rate_case",
            return_value=self._infra_case(infra_rates or {}),
        )
        with tenant_context(handler.tenant), flag_patch, infra_patch:
            handler.__dict__.pop("exchange_rate_annotation_dict", None)
            return (
                handler.query_table.objects.filter(id=row_id)
                .annotate(**handler.annotations)
                .values("date")
                .annotate(
                    **{
                        key: handler.report_annotations[key]
                        for key in ("base_currency", "exchange_rate")
                        if key in handler.report_annotations
                    }
                )
                .get()
            )

    def test_standalone_ocp_csv_falls_back_to_cost_model_currency(self):
        """NULL raw_currency uses cost-model currency and rate in CSV audit columns."""
        for constant_currency in (False, True):
            with self.subTest(constant_currency=constant_currency):
                handler, source_uuid = self._handler()
                row_id = uuid4()
                with tenant_context(handler.tenant):
                    handler.query_table.objects.create(
                        id=row_id,
                        cluster_id="csv-standalone-ocp",
                        usage_start=handler.start_datetime.date(),
                        usage_end=handler.start_datetime.date(),
                        source_uuid_id=source_uuid,
                        raw_currency=None,
                    )

                row = self._aggregate_csv_row(handler, row_id, constant_currency=constant_currency)

                self.assertEqual(row["base_currency"], "SEK")
                self.assertEqual(row["exchange_rate"], Decimal("0.095"))

    def test_ocp_on_cloud_csv_keeps_infra_currency(self):
        """Present raw_currency keeps cloud bill currency/rate in CSV audit columns."""
        for constant_currency in (False, True):
            with self.subTest(constant_currency=constant_currency):
                handler, source_uuid = self._handler()
                handler.__dict__["raw_currencies_for_conversion"] = {"EUR"}
                handler.__dict__["monthly_exchange_rate_map"] = {
                    "SEK": {handler.start_datetime.date().replace(day=1): Decimal("0.095")},
                    "EUR": {handler.start_datetime.date().replace(day=1): Decimal("1.1")},
                }
                row_id = uuid4()
                with tenant_context(handler.tenant):
                    handler.query_table.objects.create(
                        id=row_id,
                        cluster_id="csv-ocp-on-cloud",
                        usage_start=handler.start_datetime.date(),
                        usage_end=handler.start_datetime.date(),
                        source_uuid_id=source_uuid,
                        raw_currency="EUR",
                    )

                row = self._aggregate_csv_row(
                    handler,
                    row_id,
                    constant_currency=constant_currency,
                    infra_rates={"EUR": Decimal("1.1")},
                )

                self.assertEqual(row["base_currency"], "EUR")
                self.assertEqual(row["exchange_rate"], Decimal("1.1"))

    def test_standalone_without_cost_model_degrades_gracefully(self):
        """No raw_currency and no cost model still returns without raising."""
        handler, source_uuid = self._handler()
        handler.__dict__["source_to_currency_map"] = {}
        handler.__dict__["request_source_to_currency_map"] = {}
        handler.__dict__["monthly_exchange_rate_map"] = {}
        handler.__dict__["exchange_rates"] = {}
        row_id = uuid4()
        with tenant_context(handler.tenant):
            handler.query_table.objects.create(
                id=row_id,
                cluster_id="csv-no-cost-model",
                usage_start=handler.start_datetime.date(),
                usage_end=handler.start_datetime.date(),
                source_uuid_id=source_uuid,
                raw_currency=None,
            )

        row = self._aggregate_csv_row(handler, row_id, constant_currency=False)

        self.assertIsNone(row["base_currency"])
        self.assertEqual(row["exchange_rate"], Decimal("1"))

    def test_report_annotations_use_coalesce_fallback_for_base_currency(self):
        """CSV base_currency annotation is a Coalesce of infra and cost-model Max()."""
        handler, _ = self._handler()
        base_currency = handler.report_annotations["base_currency"]
        self.assertIsInstance(base_currency, Coalesce)
        self.assertIsInstance(base_currency.source_expressions[0], Max)

    def test_execute_query_csv_includes_audit_columns_for_standalone_source(self):
        """CSV execute_query populates base_currency from the cost model when raw_currency is NULL."""
        cluster_id = "csv-audit-standalone"
        query_params = self.mocked_query_params(
            "?filter[resolution]=monthly&filter[time_scope_units]=month"
            f"&filter[time_scope_value]=-1&filter[cluster]={cluster_id}",
            OCPCostView,
            path=OCP_PATH,
        )
        handler = OCPReportQueryHandler(query_params)
        handler.is_csv_output = True
        handler.currency = "USD"
        source_uuid = self.ocp_provider.uuid
        handler.__dict__["source_to_currency_map"] = {source_uuid: "SEK"}
        handler.__dict__["request_source_to_currency_map"] = {source_uuid: "SEK"}
        handler.__dict__["exchange_rates"] = {"SEK": {"USD": Decimal("0.095")}}
        with tenant_context(handler.tenant):
            handler.query_table.objects.create(
                id=uuid4(),
                cluster_id=cluster_id,
                usage_start=handler.start_datetime.date(),
                usage_end=handler.start_datetime.date(),
                source_uuid_id=source_uuid,
                raw_currency=None,
                cost_model_cpu_cost=Decimal("10.0"),
                cost_model_memory_cost=Decimal("0"),
                cost_model_volume_cost=Decimal("0"),
                infrastructure_raw_cost=Decimal("0"),
            )

        with (
            patch(FLAG_TARGET, return_value=False),
            patch("api.report.queries.is_feature_flag_enabled_by_schema", return_value=False),
            patch(
                "api.report.ocp.query_handler.build_exchange_rate_case",
                return_value=self._infra_case({}),
            ),
        ):
            handler.__dict__.pop("exchange_rate_annotation_dict", None)
            result = handler.execute_query()

        self.assertTrue(result["data"])
        for row in result["data"]:
            self.assertEqual(row.get("base_currency"), "SEK")
            self.assertEqual(Decimal(str(row.get("exchange_rate"))), Decimal("0.095"))
            self.assertEqual(row.get("cost_units"), "USD")
