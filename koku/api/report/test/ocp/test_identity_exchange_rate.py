#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the OCP source-currency identity conversion optimization."""
from unittest.mock import patch

from django.db.models import Case
from django.db.models import Value
from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from reporting.models import OCPUsageLineItemDailySummary


IDENTITY_EXCHANGE_RATE_FLAG = "cost-management.backend.ocp_report_identity_exchange_rate"
FLAG_TARGET = "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema"


class OCPIdentityExchangeRateTest(IamTestCase):
    """Verify the source-currency identity conversion rollout path."""

    def _handler(self, source_to_currency_map):
        # USD is the API default. Supplying currency explicitly invokes the
        # serializer's tenant-currency validation, which is unrelated here.
        query_params = self.mocked_query_params("?", OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        handler.__dict__["source_to_currency_map"] = source_to_currency_map
        handler.__dict__["exchange_rates"] = {"EUR": {"USD": 1.1}}
        return handler

    @staticmethod
    def _feature_flag(enabled):
        def side_effect(_schema, feature_flag, **_kwargs):
            return enabled if feature_flag == IDENTITY_EXCHANGE_RATE_FLAG else False

        return side_effect

    def _annotations(self, handler, flag_enabled):
        # The source-side expression is under test. Keep the independent
        # raw-currency builder at its boundary to avoid tenant-currency setup.
        with (
            patch(FLAG_TARGET, side_effect=self._feature_flag(flag_enabled)),
            patch("api.report.ocp.query_handler.build_exchange_rate_case", return_value=Case()),
        ):
            return handler.exchange_rate_annotation_dict

    def test_enabled_flag_uses_constant_for_identity_source_currencies(self):
        """All source cost-model currencies matching target currency use one."""
        handler = self._handler({"00000000-0000-0000-0000-000000000001": "USD"})

        annotations = self._annotations(handler, flag_enabled=True)

        self.assertIsInstance(annotations["exchange_rate"], Value)
        self.assertEqual(annotations["exchange_rate"].value, 1)
        self.assertIsInstance(annotations["infra_exchange_rate"], Case)

    def test_disabled_flag_keeps_legacy_source_currency_case(self):
        """Flag off retains the legacy conversion expression."""
        handler = self._handler({"00000000-0000-0000-0000-000000000001": "USD"})

        annotations = self._annotations(handler, flag_enabled=False)

        self.assertIsInstance(annotations["exchange_rate"], Case)

    def test_enabled_flag_keeps_case_when_a_source_needs_conversion(self):
        """Flag on must not replace a non-identity source conversion."""
        handler = self._handler({"00000000-0000-0000-0000-000000000001": "EUR"})

        annotations = self._annotations(handler, flag_enabled=True)

        self.assertIsInstance(annotations["exchange_rate"], Case)

    def _execute_identity_currency_delta_report(self, flag_enabled):
        query_params = self.mocked_query_params(
            "?delta=distributed_cost&filter[resolution]=monthly&"
            "filter[time_scope_units]=month&filter[time_scope_value]=-1&group_by[project]=*",
            OCPCostView,
            path="/api/v1/reports/openshift/costs/",
        )
        handler = OCPReportQueryHandler(query_params)
        with tenant_context(self.tenant):
            source_uuids = set(
                OCPUsageLineItemDailySummary.objects.exclude(source_uuid__isnull=True).values_list(
                    "source_uuid", flat=True
                )
            )
        self.assertTrue(source_uuids, "seeded OCP report data must contain source UUIDs")
        handler.__dict__["source_to_currency_map"] = {source_uuid: "USD" for source_uuid in source_uuids}

        with patch(FLAG_TARGET, side_effect=self._feature_flag(flag_enabled)):
            return handler.execute_query()

    def test_identity_source_currency_flag_preserves_delta_report_response(self):
        """The identity optimization must not change monthly distributed costs."""
        legacy = self._execute_identity_currency_delta_report(flag_enabled=False)
        optimized = self._execute_identity_currency_delta_report(flag_enabled=True)

        self.assertEqual(optimized, legacy)
