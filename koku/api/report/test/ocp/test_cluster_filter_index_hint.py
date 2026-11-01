#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the OCP report cluster-filter index hint."""
import json
from contextlib import nullcontext
from unittest.mock import patch

from django.db import connection
from django.db.models import Q
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.query_handler import _implied_cluster_values
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPVolumeView
from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPCostSummaryP


def _sort_value(row, field):
    """Return the value a report row is ordered by."""
    if field == "cost_total":
        return (row.get("cost") or {}).get("total", {}).get("value")
    value = row.get(field)
    return value.get("value") if isinstance(value, dict) else value


def _ranking(value, field):
    """Keep dates and each row's sort value, in output order."""
    if isinstance(value, list):
        return [_ranking(item, field) for item in value]
    if not isinstance(value, dict):
        return value
    ranking = {}
    for key, item in value.items():
        if key == "date":
            ranking[key] = item
        elif key == "values" and isinstance(item, list):
            ranking[key] = [_sort_value(row, field) for row in item]
        elif isinstance(item, list) and item and all(isinstance(row, dict) for row in item):
            ranking[key] = _ranking(item, field)
    return ranking


def _canonical_rows(value):
    """Sort report rows so tied rows compare equal in any order."""
    if isinstance(value, dict):
        return {key: _canonical_rows(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [_canonical_rows(item) for item in value]
        if items and all(isinstance(item, dict) for item in items):
            items.sort(key=lambda item: json.dumps(item, sort_keys=True, default=str))
        return items
    return value


class OCPReportClusterFilterIndexHintTest(IamTestCase):
    """Assert the index hint follows implied cluster filters."""

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

    def _handler(self, view, url, use_hint=True):
        query_params = self.mocked_query_params(url, view, path=self.OCP_PATH)
        handler = OCPReportQueryHandler(query_params)
        hint = (
            nullcontext()
            if use_hint
            else patch.object(handler, "_apply_cluster_filter_index_hint", side_effect=lambda q: q)
        )
        with hint:
            output = handler.execute_query()
        return handler, output

    def _assert_report(self, view, url, expect_data=True):
        _, report = self._handler(view, url)
        msg = f"cluster index hint changed output for {view.__name__} {url}"
        _, without_hint = self._handler(view, url, use_hint=False)
        self.assertEqual(_canonical_rows(without_hint.get("data")), _canonical_rows(report.get("data")), msg=msg)
        self.assertEqual(without_hint.get("total"), report.get("total"), msg=msg)
        self.assertIn("data", report, msg=msg)
        self.assertIn("total", report, msg=msg)
        if expect_data:
            self.assertTrue(report.get("total", {}).get("cost") or report.get("total", {}).get("usage"), msg=msg)
        return report

    def test_reports_for_cluster_filter_shapes(self):
        """Every cluster filter shape still produces the expected report data."""
        substring = self.cluster_alias[1:-1]
        filters = [
            f"filter[cluster]={self.cluster_alias}",
            f"filter[cluster]={substring}",
            f"filter[cluster]={self.cluster_id}",
            f"filter[exact:cluster]={self.cluster_alias}",
            f"filter[and:cluster]={self.cluster_alias[:4]}&filter[and:cluster]={self.cluster_alias[-4:]}",
            f"filter[or:cluster]={self.cluster_alias}&filter[or:cluster]=no-such-cluster",
            f"group_by[cluster]={self.cluster_alias}",
            # The report filter ignores these group-by values, so the hint must too.
            f"filter[cluster]=*&group_by[cluster]={self.cluster_alias}",
            f"filter[or:cluster]=*&group_by[or:cluster]={self.cluster_alias}",
            f"filter[and:cluster]=*&group_by[and:cluster]={self.cluster_alias}",
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
                        self._assert_report(view, url, expect_data=time_filter == self.LAST_MONTH)

    def test_node_reports_and_deltas(self):
        """Node capacity and delta requests retain report data."""
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
                self._assert_report(view, url)

    def test_no_matching_cluster_returns_empty_report(self):
        """A filter matching no cluster stays empty."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]=no-such-cluster"
        for view in (OCPCostView, OCPCpuView, OCPVolumeView):
            with self.subTest(view=view.__name__):
                report = self._assert_report(view, url, expect_data=False)
                self.assertTrue(report["data"])
                self.assertTrue(all(not date["projects"] for date in report["data"]))

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
                self._assert_report(view, url)
                handler, _ = self._handler(view, url)
                with schema_context(self.schema_name):
                    self.assertIn(self.source_uuid, handler._cluster_filter_source_uuids)

    def test_hint_applies_to_previous_period_total(self):
        """Both the row and total previous-period delta queries use the indexed filter."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}&delta=cost"
        with CaptureQueriesContext(connection) as captured:
            self._handler(OCPCostView, url)
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
        handler, _ = self._handler(OCPCostView, f"?{self.LAST_MONTH}&group_by[cluster]=*")
        self.assertEqual(handler._cluster_filter_values, set())

    def test_hint_adds_indexed_filters_to_report_and_capacity_queries(self):
        """Report and by-node capacity queries filter by source_uuid."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}"
        with CaptureQueriesContext(connection) as captured:
            self._handler(OCPCpuView, url)
        sql = [query["sql"] for query in captured.captured_queries]
        self.assertTrue(
            any('FROM "reporting_ocp_pod_summary_by_project_p"' in q and '"source_uuid" IN' in q for q in sql)
        )
        self.assertTrue(
            any('FROM "reporting_ocp_pod_summary_by_node_p"' in q and '"source_uuid" IN' in q for q in sql)
        )

    def test_hint_filters_daily_capacity_by_report_period(self):
        """Unsupported capacity filters keep daily-summary report-period pruning."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*&filter[cluster]={self.cluster_alias}&filter[project]=koku"
        with CaptureQueriesContext(connection) as captured:
            self._handler(OCPCpuView, url)
        sql = [query["sql"] for query in captured.captured_queries]
        self.assertTrue(
            any('FROM "reporting_ocpusagelineitem_daily_summary"' in q and '"report_period_id" IN' in q for q in sql)
        )

    def test_no_cluster_filter_adds_no_indexed_filters(self):
        """A request without a cluster restriction does not add the hint."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*"
        with CaptureQueriesContext(connection) as captured:
            self._handler(OCPCpuView, url)
        sql = [query["sql"] for query in captured.captured_queries]
        self.assertFalse(any('"report_period_id" IN' in q for q in sql))
        self.assertFalse(any('FROM "reporting_ocp_cluster' in q for q in sql))


class ImpliedClusterValuesTest(IamTestCase):
    """The hint only uses cluster values that every filtered row must match."""

    def test_and_node_uses_cluster_conditions_and_ignores_others(self):
        q = Q(usage_start__gte="2026-09-01") & (Q(cluster_alias__icontains="a") | Q(cluster_id__icontains="a"))
        self.assertEqual(_implied_cluster_values(q), {"a"})

    def test_or_node_needs_every_branch(self):
        self.assertEqual(
            _implied_cluster_values(Q(cluster_alias__icontains="a") | Q(cluster_id__exact="b")), {"a", "b"}
        )
        self.assertIsNone(_implied_cluster_values(Q(cluster_alias__icontains="a") | Q(namespace__icontains="p")))

    def test_in_lookup_and_plain_field(self):
        self.assertEqual(_implied_cluster_values(Q(cluster_id__in=["a", "b"])), {"a", "b"})
        self.assertEqual(_implied_cluster_values(Q(cluster_alias="a")), {"a"})

    def test_negation_and_non_matching_lookups_imply_nothing(self):
        self.assertIsNone(_implied_cluster_values(~Q(cluster_alias__icontains="a")))
        self.assertIsNone(_implied_cluster_values(Q(cluster_alias__isnull=False)))
        self.assertIsNone(_implied_cluster_values(Q(cluster_alias__icontains="")))
        self.assertIsNone(_implied_cluster_values(Q(namespace__icontains="p")))
