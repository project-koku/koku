#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Parity tests for the OCP report cluster-filter index hint.

``OCP_REPORT_CLUSTER_FILTER_INDEX_HINT_FLAG`` adds an indexed
``source_uuid``/``report_period_id`` restriction implied by the substring
cluster filter.  The original filter stays in place, so report output must be
identical with the flag on and off.
"""
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPVolumeView
from masu.processor import OCP_REPORT_CLUSTER_FILTER_INDEX_HINT_FLAG
from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPCostSummaryP

FLAG_TARGET = "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema"


class OCPReportClusterFilterIndexHintTest(IamTestCase):
    """Assert the index hint never changes OCP report output."""

    LAST_MONTH = "filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
    DAILY = "filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
    OCP_PATH = "/api/cost-management/v1/reports/openshift/costs/"

    def setUp(self):
        """Pick a cluster that has summarized data."""
        super().setUp()
        with schema_context(self.schema_name):
            cluster = (
                OCPCostSummaryP.objects.exclude(cluster_alias__isnull=True)
                .values("cluster_id", "cluster_alias", "source_uuid")
                .first()
            )
        self.assertIsNotNone(cluster, "test data has no OCP cost summary rows")
        self.cluster_id = cluster["cluster_id"]
        self.cluster_alias = cluster["cluster_alias"]
        self.source_uuid = cluster["source_uuid"]

    def _handler(self, view, url, hint_enabled):
        def _side_effect(schema, feature_flag, *args, **kwargs):
            if feature_flag == OCP_REPORT_CLUSTER_FILTER_INDEX_HINT_FLAG:
                return hint_enabled
            return False

        with patch(FLAG_TARGET, side_effect=_side_effect):
            query_params = self.mocked_query_params(url, view, path=self.OCP_PATH)
            handler = OCPReportQueryHandler(query_params)
            output = handler.execute_query()
        return handler, output

    def _assert_parity(self, view, url, expect_data=True):
        _, legacy = self._handler(view, url, hint_enabled=False)
        _, hinted = self._handler(view, url, hint_enabled=True)
        msg = f"cluster index hint changed output for {view.__name__} {url}"
        self.assertEqual(legacy.get("data"), hinted.get("data"), msg=msg)
        self.assertEqual(legacy.get("total"), hinted.get("total"), msg=msg)
        if expect_data:
            self.assertTrue(legacy.get("total", {}).get("cost") or legacy.get("total", {}).get("usage"), msg=msg)

    def test_parity_for_cluster_filter_shapes(self):
        """Every cluster filter shape returns the same report with the hint on."""
        substring = self.cluster_alias[1:-1]
        filters = [
            f"filter[cluster]={self.cluster_alias}",
            f"filter[cluster]={substring}",
            f"filter[cluster]={self.cluster_id}",
            f"filter[exact:cluster]={self.cluster_alias}",
            f"filter[and:cluster]={self.cluster_alias[:4]}&filter[and:cluster]={self.cluster_alias[-4:]}",
            f"filter[or:cluster]={self.cluster_alias}&filter[or:cluster]=no-such-cluster",
            f"group_by[cluster]={self.cluster_alias}",
        ]
        views = [
            (OCPCostView, "group_by[project]=*"),
            (OCPCpuView, "group_by[project]=*"),
            (OCPMemoryView, "group_by[project]=*"),
            (OCPVolumeView, "group_by[project]=*"),
        ]
        for view, group_by in views:
            for cluster_filter in filters:
                for time_filter in (self.LAST_MONTH, self.DAILY):
                    with self.subTest(view=view.__name__, cluster_filter=cluster_filter, time_filter=time_filter):
                        url = f"?{time_filter}&{group_by}&{cluster_filter}"
                        self._assert_parity(view, url, expect_data=time_filter == self.LAST_MONTH)

    def test_parity_for_node_reports_and_deltas(self):
        """Node capacity and delta queries keep the same output with the hint on."""
        urls = [
            (OCPCpuView, f"?{self.LAST_MONTH}&group_by[node]=*&filter[cluster]={self.cluster_alias}"),
            (OCPMemoryView, f"?{self.LAST_MONTH}&group_by[node]=*&filter[cluster]={self.cluster_alias}"),
            (OCPCostView, f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}&delta=cost"),
            (
                OCPCostView,
                f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}&filter[limit]=2",
            ),
        ]
        for view, url in urls:
            with self.subTest(view=view.__name__, url=url):
                self._assert_parity(view, url)

    def test_no_matching_cluster_returns_same_empty_report(self):
        """A filter matching no cluster stays empty with the hint on."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]=no-such-cluster"
        for view in (OCPCostView, OCPCpuView, OCPVolumeView):
            with self.subTest(view=view.__name__):
                self._assert_parity(view, url, expect_data=False)

    def test_renamed_cluster_still_matches_old_alias(self):
        """Rows summarized under a previous alias are still found after a rename."""
        with schema_context(self.schema_name):
            # Test data uses the cluster ID as the alias, so change both to make
            # sure only the historical cost summary lookup can match.
            OCPCluster.objects.filter(provider_id=self.source_uuid).update(
                cluster_id="renamed-cluster-id", cluster_alias="renamed-cluster"
            )
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}"
        for view in (OCPCostView, OCPCpuView):
            with self.subTest(view=view.__name__):
                self._assert_parity(view, url)
                handler, _ = self._handler(view, url, hint_enabled=True)
                with schema_context(self.schema_name):
                    self.assertIn(self.source_uuid, handler._cluster_filter_source_uuids)

    def test_hint_applies_to_previous_period_total(self):
        """Both the row and total previous-period delta queries use the indexed filter."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}&delta=cost"
        with CaptureQueriesContext(connection) as captured:
            self._handler(OCPCostView, url, hint_enabled=True)
        cluster_filtered = [
            query["sql"]
            for query in captured.captured_queries
            if 'FROM "reporting_ocp_cost_summary_by_project_p"' in query["sql"]
            and '"cluster_alias"::text) LIKE' in query["sql"]
        ]
        self.assertTrue(cluster_filtered)
        self.assertTrue(all('"source_uuid" IN' in sql for sql in cluster_filtered))

    def test_wildcard_cluster_filter_does_not_enable_hint(self):
        """group_by[cluster]=* does not filter, so no hint is added."""
        handler, _ = self._handler(OCPCostView, f"?{self.LAST_MONTH}&group_by[cluster]=*", hint_enabled=True)
        self.assertEqual(handler._cluster_filter_values, set())
        self.assertFalse(handler._cluster_filter_index_hint_enabled)

    def test_hint_adds_indexed_filters_to_report_and_capacity_queries(self):
        """Summary queries filter by source_uuid and the capacity query by report_period_id."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}"
        with CaptureQueriesContext(connection) as captured:
            self._handler(OCPCpuView, url, hint_enabled=True)
        sql = [query["sql"] for query in captured.captured_queries]
        self.assertTrue(
            any('FROM "reporting_ocp_pod_summary_by_project_p"' in q and '"source_uuid" IN' in q for q in sql)
        )
        self.assertTrue(
            any('FROM "reporting_ocpusagelineitem_daily_summary"' in q and '"report_period_id" IN' in q for q in sql)
        )

    def test_flag_off_adds_no_indexed_filters(self):
        """With the flag off, report queries are unchanged."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}"
        with CaptureQueriesContext(connection) as captured:
            self._handler(OCPCpuView, url, hint_enabled=False)
        sql = [query["sql"] for query in captured.captured_queries]
        self.assertFalse(any('"report_period_id" IN' in q for q in sql))
        self.assertFalse(any('FROM "reporting_ocp_cluster' in q for q in sql))
