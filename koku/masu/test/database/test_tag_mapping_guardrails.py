#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Exercise cloud tag mapping through the shared PostgreSQL guardrails."""
from contextlib import nullcontext
from itertools import product
from unittest.mock import Mock
from unittest.mock import patch

from django.db import connection
from django.db import OperationalError
from django.test import override_settings
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context
from model_bakery import baker

from api.models import Provider
from koku.database_exc import ExtendedDBException
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.database.tag_mapping_guardrails import run_tag_mapping_update
from masu.database.tag_mapping_guardrails import tag_mapping_statement_timeout
from masu.processor import OCP_TAG_MAPPING_DIAGNOSTICS_FLAG
from masu.processor import OCP_TAG_MAPPING_MATERIALIZED_CANDIDATES_FLAG
from masu.processor import OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG
from masu.test import MasuTestCase
from reporting.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.models import OCPAzureTagsSummary
from reporting.models import OCPGCPCostLineItemProjectDailySummaryP
from reporting.models import OCPGCPTagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping


class CloudTagMappingGuardrailsTest(MasuTestCase):
    """Keep the accessors, templates, shared runner, and database work real."""

    @override_settings(OCP_TAG_MAPPING_STATEMENT_TIMEOUT_MS=60000)
    def test_azure_guardrails(self):
        self._assert_cloud_guardrails(
            Provider.PROVIDER_AZURE,
            AzureReportDBAccessor(self.schema),
            OCPAzureCostLineItemProjectDailySummaryP,
            OCPAzureTagsSummary,
        )

    @override_settings(OCP_TAG_MAPPING_STATEMENT_TIMEOUT_MS=60000)
    def test_gcp_guardrails(self):
        self._assert_cloud_guardrails(
            Provider.PROVIDER_GCP,
            GCPReportDBAccessor(self.schema),
            OCPGCPCostLineItemProjectDailySummaryP,
            OCPGCPTagsSummary,
        )

    def _assert_cloud_guardrails(self, provider_type, accessor, model, summary_model):
        with schema_context(self.schema):
            parent = baker.make(EnabledTagKeys, key="guardrail-parent", provider_type=provider_type)
            child = baker.make(EnabledTagKeys, key="guardrail-child", provider_type=provider_type)
            baker.make(TagMapping, parent=parent, child=child)
            sample = model.objects.filter(usage_start=self.dh.this_month_start.date()).first()
            self.assertIsNotNone(sample)
            other_bill = type(sample.cost_entry_bill).objects.exclude(pk=sample.cost_entry_bill_id).first()
            self.assertIsNotNone(other_bill)
            rows = [
                baker.make(
                    model,
                    cost_entry_bill=bill,
                    report_period=sample.report_period,
                    usage_start=self.dh.today,
                    usage_end=self.dh.today,
                    namespace="guardrail-project",
                    node="guardrail-node",
                    tags={child.key: "secret-tag-value"},
                )
                for bill in (sample.cost_entry_bill, other_bill)
            ]
            selected, excluded = rows

        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            original = cursor.fetchone()[0]
            cursor.execute("SELECT set_config('statement_timeout', '0', false)")
        try:
            for materialized, diagnostics, timeout in product((False, True), repeat=3):
                with self.subTest(materialized=materialized, diagnostics=diagnostics, timeout=timeout):
                    with schema_context(self.schema):
                        model.objects.filter(pk__in=[selected.pk, excluded.pk]).update(
                            tags={child.key: "secret-tag-value"}
                        )
                    enabled = {
                        OCP_TAG_MAPPING_MATERIALIZED_CANDIDATES_FLAG: materialized,
                        OCP_TAG_MAPPING_DIAGNOSTICS_FLAG: diagnostics,
                        OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG: timeout,
                    }
                    with (
                        patch(
                            f"{type(accessor).__module__}.is_feature_flag_enabled_by_schema",
                            side_effect=lambda schema, flag, **kwargs: enabled[flag],
                        ) as flags,
                        self.assertLogs("masu.database.tag_mapping_guardrails", level="INFO")
                        if diagnostics
                        else nullcontext() as logged,
                        CaptureQueriesContext(connection) as captured,
                    ):
                        getattr(accessor, f"populate_ocp_on_{provider_type.lower()}_tag_information")(
                            [selected.cost_entry_bill_id], self.dh.today, self.dh.today, selected.report_period_id
                        )
                    self.assertCountEqual(
                        flags.call_args_list,
                        [((self.schema, flag), {"dev_fallback": True}) for flag in enabled],
                    )
                    queries = [query["sql"] for query in captured.captured_queries]
                    updates = [
                        q for q in queries if "SET tags = update_data.update_tags" in q and not q.startswith("EXPLAIN")
                    ]
                    self.assertEqual(len(updates), 1)
                    self.assertEqual("cte_update_tag_keys as MATERIALIZED" in updates[0], materialized)
                    self.assertEqual(sum(q.startswith("EXPLAIN (FORMAT JSON)") for q in queries), int(diagnostics))
                    config = [q for q in queries if "set_config('statement_timeout'" in q]
                    self.assertEqual(len(config), 2 * int(timeout))
                    if timeout:
                        self.assertIn("'60000'", config[0])
                        self.assertIn("'0'", config[1])
                        self.assertLess(queries.index(config[0]), queries.index(updates[0]))
                        self.assertLess(queries.index(updates[0]), queries.index(config[1]))
                    with connection.cursor() as cursor:
                        cursor.execute("SHOW statement_timeout")
                        self.assertEqual(cursor.fetchone()[0], "0")
                    if diagnostics:
                        plan = logged.records[0].msg
                        self.assertEqual(plan["report_period_ids"], selected.report_period_id)
                        self.assertTrue(plan["plan_nodes"])
                        self.assertNotIn("secret-tag-value", str(plan))
                    with schema_context(self.schema):
                        selected.refresh_from_db()
                        excluded.refresh_from_db()
                        self.assertEqual(selected.tags, {parent.key: "secret-tag-value"})
                        self.assertEqual(excluded.tags, {child.key: "secret-tag-value"})
                        self.assertEqual(
                            list(
                                summary_model.objects.filter(
                                    key=parent.key, cost_entry_bill=selected.cost_entry_bill
                                ).values_list("values", flat=True)
                            ),
                            [["secret-tag-value"]],
                        )
                        self.assertFalse(
                            summary_model.objects.filter(
                                key__in=[parent.key, child.key], cost_entry_bill=other_bill
                            ).exists()
                        )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('statement_timeout', %s, false)", [original])


class TagMappingRunnerTest(SimpleTestCase):
    """Exercise timeout failure handling without a TestCase transaction."""

    databases = {"default"}

    @override_settings(OCP_TAG_MAPPING_STATEMENT_TIMEOUT_MS=10)
    def test_restore_failure_closes_connection_and_preserves_update_error(self):
        """Never return a connection with a leaked timeout or hide the UPDATE error."""
        for update_error in (None, RuntimeError("update failed")):
            with self.subTest(update_error=update_error):
                restore_error = OperationalError("connection lost during restore")
                expected_error = update_error if update_error is not None else restore_error
                with patch("masu.database.tag_mapping_guardrails.connection") as db:
                    cursor = db.cursor.return_value.__enter__.return_value
                    cursor.fetchone.return_value = ("0", 0)
                    cursor.execute.side_effect = [None, None, restore_error]
                    with (
                        self.assertLogs("masu.database.tag_mapping_guardrails", level="ERROR"),
                        self.assertRaises(type(expected_error)) as raised,
                        tag_mapping_statement_timeout("public"),
                    ):
                        if update_error is not None:
                            raise update_error
                    self.assertIs(raised.exception, expected_error)
                    cursor.execute.assert_called_with("SELECT set_config('statement_timeout', %s, false)", ["0"])
                    db.close.assert_called_once_with()

    @override_settings(OCP_TAG_MAPPING_STATEMENT_TIMEOUT_MS=10)
    def test_cancelled_statement_logs_period_and_restores_connection(self):
        accessor = ReportDBAccessorBase(schema="public")
        for period_params in ({"report_period_id": 7}, {"report_period_ids": [7, 8]}):
            with self.subTest(period_params=period_params):
                params = {"start_date": "2026-11-01", "end_date": "2026-11-02", **period_params}
                flags = Mock(side_effect=lambda schema, flag, **kwargs: flag == OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG)
                with connection.cursor() as cursor:
                    cursor.execute("SHOW statement_timeout")
                    original = cursor.fetchone()[0]
                with (
                    self.assertLogs("masu.database.tag_mapping_guardrails", level="ERROR") as logged,
                    self.assertRaises(ExtendedDBException) as raised,
                ):
                    run_tag_mapping_update(
                        accessor,
                        "tag mapping",
                        "SELECT pg_sleep(0.1) /* secret-tag-value */",
                        params,
                        label="OCP-on-GCP",
                        flag_checker=flags,
                    )
                self.assertEqual(raised.exception.pgcode, "57014")
                failure = logged.records[0].msg
                self.assertEqual(failure["message"], "OCP-on-GCP tag-mapping UPDATE failed")
                self.assertEqual(failure["report_period_ids"], next(iter(period_params.values())))
                self.assertEqual(failure["effective_timeout_ms"], 10)
                self.assertEqual(failure["pgcode"], "57014")
                self.assertNotIn("secret-tag-value", str(failure))
                with connection.cursor() as cursor:
                    cursor.execute("SHOW statement_timeout")
                    self.assertEqual(cursor.fetchone()[0], original)
                    cursor.execute("SELECT 1")
                    self.assertEqual(cursor.fetchone()[0], 1)
