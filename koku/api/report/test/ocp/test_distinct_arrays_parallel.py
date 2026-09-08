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

from django_tenants.utils import schema_context
from model_bakery import baker

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPMigProfilesView
from api.report.ocp.view import OCPNetworkView
from api.report.ocp.view import OCPVolumeView
from masu.processor import OCP_REPORT_DISTINCT_ARRAYS_PARALLEL_FLAG
from reporting.provider.ocp.models import OCPGpuSummaryP

FLAG_TARGET = "api.report.ocp.query_handler.is_feature_flag_enabled_by_schema"


def _collect_metadata_arrays(node, acc):
    """Recursively collect clusters/source_uuid arrays from a report response.

    Returns a mapping of a stable row identity (the frozenset of the leaf row's
    string-valued fields -- date plus the group-by labels) to the *sets* of
    clusters/source_uuid and the node capacity count found on that row.
    """
    if isinstance(node, dict):
        if "source_uuid" in node or "clusters" in node:
            key = frozenset(
                (k, v)
                for k, v in node.items()
                if isinstance(v, str) and k not in {"clusters", "source_uuid", "capacity_count"}
            )
            entry = acc.setdefault(key, {"source_uuid": set(), "clusters": set(), "capacity_count": None})
            entry["source_uuid"] |= {str(v) for v in (node.get("source_uuid") or [])}
            entry["clusters"] |= {str(v) for v in (node.get("clusters") or [])}
            if "capacity_count" in node:
                entry["capacity_count"] = node["capacity_count"]
            elif isinstance(capacity := node.get("capacity"), dict):
                count = capacity.get("count")
                entry["capacity_count"] = count.get("value") if isinstance(count, dict) else count
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
            split = self._run_and_collect(view, url, split_enabled=True, csv_output=csv_output)
            legacy = self._run_and_collect(view, url, split_enabled=False, csv_output=csv_output)
            self.assertEqual(
                legacy,
                split,
                msg=f"metadata/capacity-count parity failed for {view.__name__} {url}",
            )
            # Guard against the degenerate case where both are empty (would make
            # the equality assertion vacuous). Every case below has data.
            self.assertTrue(legacy, msg=f"no metadata arrays collected for {view.__name__} {url}")
            if "group_by[node]" in suffix and view.report in {"cpu", "memory", "volume"}:
                node_counts = [
                    metadata["capacity_count"]
                    for key, metadata in split.items()
                    if any(field == "node" for field, _ in key)
                ]
                self.assertTrue(node_counts, msg=f"no node capacity counts collected for {view.__name__} {url}")
                self.assertTrue(
                    all(count is not None for count in node_counts),
                    msg=f"missing node capacity count for {view.__name__} {url}",
                )

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
            # With an order field already in rank_group_by, the moved arrays
            # must not be the only aggregate that preserves SQL grouping.
            (OCPCpuView, "group_by[cluster]=*&order_by[cluster]=asc&filter[limit]=2"),
        ]
        self._assert_parity(matrix)

    def test_mig_profiles_limit_groups_before_ranking_when_split_enabled(self):
        """The split path must rank distinct MIG instances, not source rows."""
        vendor = "nvidia-distinct-arrays"
        model = "A100-distinct-arrays"
        node = "node-distinct-arrays"
        rows = [
            {"mig_profile": "1g.5gb", "mig_instance_id": "MIG-DISTINCT-0001"},
            {"mig_profile": "1g.5gb", "mig_instance_id": "MIG-DISTINCT-0002"},
            {"mig_profile": "1g.5gb", "mig_instance_id": "MIG-DISTINCT-0003"},
            {"mig_profile": "4g.20gb", "mig_instance_id": "MIG-DISTINCT-0004"},
        ]
        with schema_context(self.schema_name):
            for row in rows:
                baker.make(
                    OCPGpuSummaryP,
                    vendor_name=vendor,
                    model_name=model,
                    node=node,
                    gpu_mode="MIG",
                    raw_currency="USD",
                    **row,
                )

        url = f"?filter[gpu_vendor]={vendor}&filter[gpu_model]={model}&filter[node]={node}" "&filter[limit]=3"
        with patch(FLAG_TARGET, return_value=True):
            query_params = self.mocked_query_params(
                url,
                OCPMigProfilesView,
                path="/api/cost-management/v1/reports/openshift/gpu/mig_profiles/",
            )
            output = OCPReportQueryHandler(query_params).execute_query()

        returned = sum(
            len(profile.get("values", [])) for entry in output["data"] for profile in entry.get("mig_profiles", [])
        )
        self.assertEqual(returned, 3)

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
