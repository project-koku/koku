#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Parity tests for the OCP report distinct-arrays parallelization split.

The ``OCP_REPORT_DISTINCT_ARRAYS_PARALLEL_FLAG`` moves the ``clusters`` and
``source_uuid`` ``ARRAY_AGG(DISTINCT ...)`` annotations out of the heavy
aggregation queries and into separate cheap queries so the main aggregation can
parallelize.  The arrays' values must be identical to the legacy (flag-off)
output.  These tests assert that parity, comparing the arrays as *sets* (the
order returned by ``ARRAY_AGG`` is not guaranteed and may differ between the two
paths).
"""
from unittest.mock import patch

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPNetworkView
from api.report.ocp.view import OCPVolumeView
from masu.processor import OCP_REPORT_DISTINCT_ARRAYS_PARALLEL_FLAG

FLAG_TARGET = "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema"


def _collect_metadata_arrays(node, acc):
    """Recursively collect clusters/source_uuid arrays from a report response.

    Returns a mapping of a stable row identity (the frozenset of the leaf row's
    string-valued fields -- date plus the group-by labels) to the *sets* of
    clusters and source_uuid found on that row.
    """
    if isinstance(node, dict):
        if "source_uuid" in node or "clusters" in node:
            key = frozenset((k, v) for k, v in node.items() if isinstance(v, str))
            entry = acc.setdefault(key, {"source_uuid": set(), "clusters": set()})
            entry["source_uuid"] |= {str(v) for v in (node.get("source_uuid") or [])}
            entry["clusters"] |= {str(v) for v in (node.get("clusters") or [])}
        for value in node.values():
            _collect_metadata_arrays(value, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_metadata_arrays(item, acc)
    return acc


class OCPReportDistinctArraysParallelTest(IamTestCase):
    """Assert the split path reproduces the legacy clusters/source_uuid output."""

    # Explicit last-month monthly window guarantees loaded data regardless of
    # where "today" falls in the current month.
    LAST_MONTH = "filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly"
    # Real OCP endpoints all contain "openshift" in the path, so is_openshift is
    # always True in production; force it here (mocked requests lack a real path).
    OCP_PATH = "/api/cost-management/v1/reports/openshift/costs/"

    def _run_and_collect(self, view, url, split_enabled, csv_output=False):
        """Execute an OCP report with the split flag on/off and collect arrays."""

        def _side_effect(schema, feature_flag, *args, **kwargs):
            if feature_flag == OCP_REPORT_DISTINCT_ARRAYS_PARALLEL_FLAG:
                return split_enabled
            return False

        with patch(FLAG_TARGET, side_effect=_side_effect):
            query_params = self.mocked_query_params(url, view, path=self.OCP_PATH)
            handler = OCPReportQueryHandler(query_params)
            handler.is_csv_output = csv_output
            output = handler.execute_query()
        return _collect_metadata_arrays(output, {})

    def _assert_parity(self, matrix, csv_output=False):
        for view, suffix in matrix:
            url = f"?{self.LAST_MONTH}&{suffix}" if suffix else f"?{self.LAST_MONTH}"
            legacy = self._run_and_collect(view, url, split_enabled=False, csv_output=csv_output)
            split = self._run_and_collect(view, url, split_enabled=True, csv_output=csv_output)
            self.assertEqual(
                legacy,
                split,
                msg=f"clusters/source_uuid parity failed for {view.__name__} {url}",
            )
            # Guard against the degenerate case where both are empty (would make
            # the equality assertion vacuous). Every case below has data.
            self.assertTrue(legacy, msg=f"no metadata arrays collected for {view.__name__} {url}")

    def test_distinct_arrays_parity_no_limit(self):
        """Split path matches legacy arrays without filter[limit] (main query)."""
        matrix = [
            (OCPCostView, "group_by[project]=*"),
            (OCPCostView, "group_by[node]=*"),
            (OCPCostView, "group_by[cluster]=*"),
            (OCPCpuView, "group_by[project]=*"),
            (OCPMemoryView, "group_by[node]=*"),
            (OCPVolumeView, "group_by[project]=*"),
            (OCPNetworkView, "group_by[project]=*"),
            (OCPCostView, ""),
        ]
        self._assert_parity(matrix)

    def test_distinct_arrays_parity_with_limit(self):
        """Split path matches legacy arrays with filter[limit] (rank + Others)."""
        matrix = [
            (OCPCostView, "group_by[project]=*&filter[limit]=2"),
            (OCPCostView, "group_by[node]=*&filter[limit]=2"),
            (OCPCpuView, "group_by[cluster]=*&filter[limit]=1"),
            (OCPCostView, "group_by[project]=*&filter[limit]=1"),
        ]
        self._assert_parity(matrix)

    def test_distinct_arrays_parity_with_category(self):
        """Split path matches legacy arrays when a category param is active."""
        matrix = [
            (OCPCostView, "group_by[project]=*&category=*"),
            (OCPCostView, "group_by[project]=*&category=*&filter[limit]=2"),
        ]
        # category=* resolves cost categories via OpenshiftCostCategory; mock it the
        # same way the existing classification tests do (table isn't populated here).
        with patch("reporting.provider.ocp.models.OpenshiftCostCategory.objects") as mock_object:
            mock_object.values_list.return_value.distinct.return_value = ["Platform"]
            self._assert_parity(matrix)

    def test_distinct_arrays_parity_csv_output(self):
        """Split path matches legacy arrays for CSV (flat) output."""
        matrix = [
            (OCPCostView, "group_by[project]=*"),
            (OCPCostView, "group_by[node]=*&filter[limit]=2"),
        ]
        self._assert_parity(matrix, csv_output=True)
