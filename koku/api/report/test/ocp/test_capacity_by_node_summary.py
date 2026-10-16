#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for reading OCP CPU/memory capacity from the by-node summary."""
from contextlib import nullcontext
from unittest.mock import patch

from django.db import connection
from django.db.models import Exists
from django.db.models import F
from django.db.models import Q
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.query_handler import _q_uses_only_fields
from api.report.ocp.query_handler import CAPACITY_BY_NODE_SUMMARY_FILTER_FIELDS
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPVolumeView
from reporting.provider.ocp.models import OCPPodSummaryByNodeP

FLAG_TARGET = "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema"
BY_NODE_TABLE = '"reporting_ocp_pod_summary_by_node_p"'
DAILY_SUMMARY_TABLE = '"reporting_ocpusagelineitem_daily_summary"'


class OCPCapacityByNodeSummaryTest(IamTestCase):
    """Assert capacity uses the by-node source only for supported shapes."""

    LAST_MONTH = "filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
    DAILY = "filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=daily"
    OCP_PATH = "/api/cost-management/v1/reports/openshift/compute/"

    def setUp(self):
        """Pick a cluster and node that have by-node summary data."""
        super().setUp()
        with schema_context(self.schema_name):
            row = (
                OCPPodSummaryByNodeP.objects.exclude(cluster_alias__isnull=True)
                .exclude(node__isnull=True)
                .values("cluster_alias", "node")
                .first()
            )
        self.assertIsNotNone(row, "test data has no OCP by-node summary rows")
        self.cluster_alias = row["cluster_alias"]
        self.node = row["node"]

    def _run(self, view, url, use_by_node=True):
        with patch(FLAG_TARGET, return_value=False):
            query_params = self.mocked_query_params(url, view, path=self.OCP_PATH)
            handler = OCPReportQueryHandler(query_params)
            table = (
                nullcontext()
                if use_by_node
                else patch.object(handler, "_capacity_query_table", return_value=handler._mapper.query_table)
            )
            with table, CaptureQueriesContext(connection) as captured:
                output = handler.execute_query()
        return output, [query["sql"] for query in captured.captured_queries]

    def _assert_capacity_report(self, view, url):
        report, sql = self._run(view, url)
        daily_report, _ = self._run(view, url, use_by_node=False)
        msg = f"by-node capacity report failed for {view.__name__} {url}"
        self.assertEqual(daily_report.get("data"), report.get("data"), msg=msg)
        self.assertEqual(daily_report.get("total"), report.get("total"), msg=msg)
        self.assertIn("data", report, msg=msg)
        self.assertTrue(report.get("total", {}).get("capacity"), msg=msg)
        return sql

    def test_supported_shapes_read_by_node_summary(self):
        """CPU and memory capacity reads the by-node summary for supported filters."""
        filters = [
            "",
            "&group_by[project]=*",
            "&group_by[cluster]=*",
            "&group_by[node]=*",
            f"&group_by[project]=*&filter[cluster]={self.cluster_alias}",
            f"&group_by[node]=*&filter[cluster]={self.cluster_alias}",
            f"&group_by[cluster]=*&filter[node]={self.node}",
            f"&group_by[project]=*&exclude[cluster]={self.cluster_alias}",
        ]
        for view in (OCPCpuView, OCPMemoryView):
            for time_filter in (self.LAST_MONTH, self.DAILY):
                for extra in filters:
                    url = f"?{time_filter}{extra}"
                    with self.subTest(view=view.__name__, url=url):
                        sql = self._assert_capacity_report(view, url)
                        self.assertTrue(any(BY_NODE_TABLE in q for q in sql), msg=url)
                        self.assertFalse(any(DAILY_SUMMARY_TABLE in q for q in sql), msg=url)

    def test_unsupported_filters_keep_daily_summary(self):
        """Filters the by-node summary cannot express keep reading the daily summary."""
        cases = [
            (OCPCpuView, f"?{self.LAST_MONTH}&group_by[project]=*&filter[project]=a"),
            (OCPCpuView, f"?{self.LAST_MONTH}&group_by[cluster]=*&exclude[project]=a"),
            (OCPMemoryView, f"?{self.LAST_MONTH}&group_by[project]=*&filter[category]=a"),
            (OCPCpuView, f"?{self.LAST_MONTH}&group_by[tag:app]=*"),
        ]
        for view, url in cases:
            with self.subTest(view=view.__name__, url=url):
                report, sql = self._run(view, url)
                self.assertIn("data", report)
                self.assertTrue(report.get("total", {}).get("capacity"))
                capacity_sql = [q for q in sql if "capacity" in q]
                self.assertTrue(capacity_sql, msg=url)
                self.assertFalse(any(BY_NODE_TABLE in q and "capacity" in q for q in capacity_sql), msg=url)

    def test_volume_reports_keep_daily_summary(self):
        """Volume capacity is not stored in the by-node summary."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*"
        _, sql = self._run(OCPVolumeView, url)
        self.assertFalse(any(BY_NODE_TABLE in q for q in sql))
        self.assertTrue(any(DAILY_SUMMARY_TABLE in q and "capacity" in q for q in sql))

    def test_project_filter_reads_daily_summary(self):
        """A project filter cannot be evaluated on the by-node summary."""
        _, sql = self._run(OCPCpuView, f"?{self.LAST_MONTH}&group_by[project]=*&filter[project]=a")
        self.assertFalse(any(BY_NODE_TABLE in q for q in sql))
        self.assertTrue(any(DAILY_SUMMARY_TABLE in q and "capacity" in q for q in sql))


class QUsesOnlyFieldsTest(IamTestCase):
    """The by-node summary is used only when every filter lookup is a plain value on an allowed field."""

    def test_allowed_fields_including_nested_q(self):
        q = Q(usage_start__gte="2026-09-01") & (Q(cluster_alias__icontains="a") | Q(node="n"))
        self.assertTrue(_q_uses_only_fields(q, CAPACITY_BY_NODE_SUMMARY_FILTER_FIELDS))

    def test_disallowed_field_in_nested_q(self):
        q = Q(usage_start__gte="2026-09-01") & (Q(cluster_alias__icontains="a") | Q(namespace__icontains="p"))
        self.assertFalse(_q_uses_only_fields(q, CAPACITY_BY_NODE_SUMMARY_FILTER_FIELDS))

    def test_expression_value_is_not_allowed(self):
        self.assertFalse(_q_uses_only_fields(Q(node=F("cluster_id")), CAPACITY_BY_NODE_SUMMARY_FILTER_FIELDS))

    def test_non_lookup_child_is_not_allowed(self):
        q = Q(Exists(OCPPodSummaryByNodeP.objects.all()))
        self.assertFalse(_q_uses_only_fields(q, CAPACITY_BY_NODE_SUMMARY_FILTER_FIELDS))
