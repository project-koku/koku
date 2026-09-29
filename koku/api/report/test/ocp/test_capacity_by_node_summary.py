#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Parity tests for reading OCP CPU/memory capacity from the by-node summary.

``OCP_CAPACITY_BY_NODE_SUMMARY_FLAG`` reads capacity for CPU and memory reports
from ``reporting_ocp_pod_summary_by_node_p`` instead of the daily summary when
every filter can be applied to it.  Report output must be identical with the
flag on and off.
"""
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPVolumeView
from masu.processor import OCP_CAPACITY_BY_NODE_SUMMARY_FLAG
from masu.processor import OCP_CAPACITY_SINGLE_SCAN_FLAG
from reporting.provider.ocp.models import OCPPodSummaryByNodeP

FLAG_TARGET = "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema"
BY_NODE_TABLE = '"reporting_ocp_pod_summary_by_node_p"'
DAILY_SUMMARY_TABLE = '"reporting_ocpusagelineitem_daily_summary"'


class OCPCapacityByNodeSummaryTest(IamTestCase):
    """Assert the by-node capacity source never changes CPU/memory report output."""

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

    def _run(self, view, url, by_node_enabled, single_scan_enabled=False):
        def _side_effect(schema, feature_flag, *args, **kwargs):
            if feature_flag == OCP_CAPACITY_BY_NODE_SUMMARY_FLAG:
                return by_node_enabled
            if feature_flag == OCP_CAPACITY_SINGLE_SCAN_FLAG:
                return single_scan_enabled
            return False

        with patch(FLAG_TARGET, side_effect=_side_effect):
            query_params = self.mocked_query_params(url, view, path=self.OCP_PATH)
            handler = OCPReportQueryHandler(query_params)
            with CaptureQueriesContext(connection) as captured:
                output = handler.execute_query()
        return output, [query["sql"] for query in captured.captured_queries]

    def _assert_parity(self, view, url, single_scan_enabled=False):
        legacy, _ = self._run(view, url, by_node_enabled=False, single_scan_enabled=single_scan_enabled)
        by_node, sql = self._run(view, url, by_node_enabled=True, single_scan_enabled=single_scan_enabled)
        msg = f"by-node capacity changed output for {view.__name__} {url}"
        self.assertEqual(legacy.get("data"), by_node.get("data"), msg=msg)
        self.assertEqual(legacy.get("total"), by_node.get("total"), msg=msg)
        self.assertTrue(legacy.get("total", {}).get("capacity"), msg=msg)
        return sql

    def test_parity_for_supported_shapes(self):
        """CPU and memory reports return the same output when capacity reads the by-node summary."""
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
                    for single_scan in (False, True):
                        url = f"?{time_filter}{extra}"
                        with self.subTest(view=view.__name__, url=url, single_scan=single_scan):
                            sql = self._assert_parity(view, url, single_scan_enabled=single_scan)
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
                legacy, _ = self._run(view, url, by_node_enabled=False)
                by_node, sql = self._run(view, url, by_node_enabled=True)
                self.assertEqual(legacy.get("data"), by_node.get("data"))
                self.assertEqual(legacy.get("total"), by_node.get("total"))
                capacity_sql = [q for q in sql if "capacity" in q]
                self.assertTrue(capacity_sql, msg=url)
                self.assertFalse(any(BY_NODE_TABLE in q and "capacity" in q for q in capacity_sql), msg=url)

    def test_volume_reports_keep_daily_summary(self):
        """Volume capacity is not stored in the by-node summary."""
        url = f"?{self.LAST_MONTH}&group_by[project]=*"
        _, sql = self._run(OCPVolumeView, url, by_node_enabled=True)
        self.assertFalse(any(BY_NODE_TABLE in q for q in sql))
        self.assertTrue(any(DAILY_SUMMARY_TABLE in q and "capacity" in q for q in sql))

    def test_flag_off_reads_daily_summary(self):
        """With the flag off, capacity reads the daily summary as before."""
        _, sql = self._run(OCPCpuView, f"?{self.LAST_MONTH}&group_by[project]=*", by_node_enabled=False)
        self.assertFalse(any(BY_NODE_TABLE in q for q in sql))
        self.assertTrue(any(DAILY_SUMMARY_TABLE in q and "capacity" in q for q in sql))
