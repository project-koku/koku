#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the dataclasses."""
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.report.ocp.dataclasses.cluster_capacity import ClusterCapacity
from api.report.ocp.dataclasses.node_capacity import NodeCapacity
from api.report.ocp.provider_map import OCPProviderMap
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPVolumeView
from api.utils import DateHelper


def build_query(handler):
    q_table = handler._mapper.query_table
    query = q_table.objects.filter(handler.query_filter)
    if handler.query_exclusions:
        query = query.exclude(handler.query_exclusions)
    return query


class ClusterCapacityDataclassTest(IamTestCase):
    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()

    def test_costs_provider_map_has_required_mappings(self):
        """Test that the volume map has the required mappings."""
        for report_type in ["costs", "costs_by_project"]:
            report_type_map = OCPProviderMap(Provider.PROVIDER_OCP, report_type)._report_type_map
            self.assertEqual(report_type_map.get("capacity_aggregate"), {})

    def test_capacity_aggregate_values_in_provider_map(self):
        """Test the required structure exist in the provider map for the dataclass."""
        # Used to confirm the dictionary structure for the dataclass exists in the
        # provider map.
        for report_type in ["cpu", "memory", "volume"]:
            with self.subTest(report_type=report_type):
                report_type_map = OCPProviderMap(Provider.PROVIDER_OCP, report_type)._report_type_map
                self.assertTrue(report_type_map.get("count_units_key"))
                capacity_aggregate = report_type_map.get("capacity_aggregate")
                self.assertTrue(capacity_aggregate)
                # Confirm cluster structure in provider map
                if report_type != "volume":
                    self.assertTrue(capacity_aggregate.get("cluster"))
                    self.assertIn("capacity", capacity_aggregate["cluster"])
                    self.assertIn("cluster", capacity_aggregate["cluster"])
                # Confirm cluster instance count structure in provider map
                self.assertTrue(capacity_aggregate.get("cluster_instance_counts"))
                self.assertIn("capacity_count", capacity_aggregate["cluster_instance_counts"])
                self.assertIn("cluster", capacity_aggregate["cluster_instance_counts"])

    def test_cluster_count_mapping_property_today(self):
        """Test the cluster count mapping property"""
        _resolution = "daily"
        params = {
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": _resolution,
            "group_by[cluster]": "*",
        }
        url = "?" + urlencode(params, quote_via=quote_plus)
        for view in [OCPVolumeView, OCPCpuView, OCPMemoryView]:
            with self.subTest(view=view):
                query_params = self.mocked_query_params(url, view)
                handler = OCPReportQueryHandler(query_params)
                with tenant_context(self.tenant):
                    query = build_query(handler)
                    cluster_capacity = ClusterCapacity(handler._mapper.report_type_map, query, _resolution)
                    cluster_capacity.populate_dataclass()
                    # build expected values
                    expected_values = {}
                    cluster_capacity_vals = (
                        query.values(*["usage_start", "node"])
                        .annotate(**cluster_capacity.count_annotations)
                        .filter(usage_start=self.dh.today.date())
                    )
                    for cluster_to_node in cluster_capacity_vals:
                        cluster = cluster_to_node.get("cluster")
                        capacity_count = cluster_to_node.get("capacity_count")
                        if mapping_count := expected_values.get(cluster):
                            expected_values[cluster] = mapping_count + capacity_count
                        else:
                            expected_values[cluster] = capacity_count
                    today_str = str(self.dh.today.date())
                    for cluster, expected_count_value in expected_values.items():
                        result = cluster_capacity.count_by_date_cluster.get(today_str).get(cluster, {})
                        self.assertEqual(expected_count_value, result)

    def test_cluster_capacity_no_dataclass_field_in_provider_map(self):
        """Test that an empty directory is returned if no count annotations."""
        _resolution = "daily"
        params = {
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": _resolution,
            "group_by[cluster]": "*",
        }
        url = "?" + urlencode(params, quote_via=quote_plus)
        query_params = self.mocked_query_params(url, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        cluster_capacity = ClusterCapacity(handler._mapper.report_type_map, None, _resolution)
        self.assertFalse(cluster_capacity.populate_dataclass())

    def test_get_cluster_capacity_counts_by_cluster(self):
        """Test the volume capacities of a daily volume report with various group bys matches expected"""
        _resolution = "daily"
        params = {
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": _resolution,
            "group_by[cluster]": "*",
        }
        url = "?" + urlencode(params, quote_via=quote_plus)
        for view in [OCPVolumeView, OCPCpuView, OCPMemoryView]:
            with self.subTest(view=view):
                expected_cluster_count = {}
                expected_date_count = {}
                expected_total_count = 0
                query_params = self.mocked_query_params(url, view)
                handler = OCPReportQueryHandler(query_params)
                with tenant_context(self.tenant):
                    query = build_query(handler)
                    cluster_capacity = ClusterCapacity(handler._mapper.report_type_map, query, _resolution)
                    cluster_capacity.populate_dataclass()
                    # build expected values
                    cluster_capacity_vals = query.values(*["usage_start", "node"]).annotate(
                        **cluster_capacity.count_annotations
                    )
                    for cluster_to_node in cluster_capacity_vals:
                        cluster = cluster_to_node.get("cluster")
                        usage_start = str(cluster_to_node.get("usage_start"))
                        node_capacity_count = cluster_to_node.get("capacity_count")
                        expected_total_count += node_capacity_count
                        if cluster_count := expected_cluster_count.get(cluster):
                            expected_cluster_count[cluster] = cluster_count + node_capacity_count
                        else:
                            expected_cluster_count[cluster] = node_capacity_count
                        if cluster_count := expected_date_count.get(usage_start):
                            expected_date_count[usage_start] = cluster_count + node_capacity_count
                        else:
                            expected_date_count[usage_start] = node_capacity_count
                # validate expected values
                for cluster, cluster_expected_count in expected_cluster_count.items():
                    self.assertEqual(cluster_expected_count, cluster_capacity.count_by_cluster.get(cluster))

                for usage_date, usage_expected_count in expected_date_count.items():
                    self.assertEqual(usage_expected_count, cluster_capacity.count_by_date.get(usage_date))

    def test_capacity_aggregations(self):
        """Test the volume capacities of a daily volume report with various group bys matches expected"""
        _resolution = "daily"
        params = {
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": _resolution,
            "group_by[cluster]": "*",
        }
        url = "?" + urlencode(params, quote_via=quote_plus)
        for view in [OCPCpuView, OCPMemoryView]:
            with self.subTest(view=view):
                expected_cluster_capacity = {}
                expected_date_capacity = {}
                expected_total_capacity = 0
                query_params = self.mocked_query_params(url, view)
                handler = OCPReportQueryHandler(query_params)
                with tenant_context(self.tenant):
                    query = build_query(handler)
                    cluster_capacity = ClusterCapacity(handler._mapper.report_type_map, query, _resolution)
                    cluster_capacity.populate_dataclass()
                    # build expected values
                    expected_query = query.values(*["usage_start", "cluster_id"]).annotate(
                        **cluster_capacity.capacity_annotations
                    )
                    for row in expected_query:
                        usage_start = str(row.get("usage_start"))
                        cluster = row.get("cluster_id")
                        expected_capacity = row.get("capacity")
                        expected_total_capacity += expected_capacity
                        result_value = cluster_capacity.capacity_by_date_cluster.get(usage_start, {}).get(cluster)
                        self.assertEqual(result_value, expected_capacity)
                        if current_cluster_capacity := expected_cluster_capacity.get(cluster):
                            expected_cluster_capacity[cluster] = current_cluster_capacity + expected_capacity
                        else:
                            expected_cluster_capacity[cluster] = expected_capacity
                        if current_usage_capacity := expected_date_capacity.get(usage_start):
                            expected_date_capacity[usage_start] = current_usage_capacity + expected_capacity
                        else:
                            expected_date_capacity[usage_start] = expected_capacity
                    for usage_date, expected_usage_capacity in expected_date_capacity.items():
                        self.assertEqual(cluster_capacity.capacity_by_date[usage_date], expected_usage_capacity)
                    for cluster, _expected_cluster_capacity in expected_cluster_capacity.items():
                        self.assertEqual(cluster_capacity.capacity_by_cluster.get(cluster), _expected_cluster_capacity)
                    self.assertEqual(expected_total_capacity, cluster_capacity.capacity_total)


class NodeCapacityDataclassTest(IamTestCase):
    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

    def test_costs_provider_map_has_required_mappings(self):
        """Test that the volume map has the required mappings."""
        for report_type in ["costs", "costs_by_project"]:
            report_type_map = OCPProviderMap(Provider.PROVIDER_OCP, report_type)._report_type_map
            self.assertEqual(report_type_map.get("capacity_aggregate"), {})

    def test_capacity_aggregate_values_in_provider_map(self):
        """Test the required structure exist in the provider map for the dataclass."""
        # Used to confirm the dictionary structure for the dataclass exists in the
        # provider map.
        for report_type in ["cpu", "memory", "volume"]:
            with self.subTest(report_type=report_type):
                report_type_map = OCPProviderMap(Provider.PROVIDER_OCP, report_type)._report_type_map
                self.assertTrue(report_type_map.get("count_units_key"))
                capacity_aggregate = report_type_map.get("capacity_aggregate")
                self.assertTrue(capacity_aggregate)
                # Confirm node structure exists in the provider map
                self.assertTrue(capacity_aggregate.get("node"))
                self.assertIn("capacity_count", capacity_aggregate["node"])
                self.assertIn("capacity", capacity_aggregate["node"])

    def test_capacity_aggregations(self):
        """Test the volume capacities of a daily volume report with various group bys matches expected"""
        _resolution = "daily"
        params = {
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": _resolution,
            "group_by[node]": "*",
        }
        url = "?" + urlencode(params, quote_via=quote_plus)
        for view in [OCPVolumeView, OCPCpuView, OCPMemoryView]:
            with self.subTest(view=view):
                expected_total_capacity = 0
                query_params = self.mocked_query_params(url, view)
                handler = OCPReportQueryHandler(query_params)
                with tenant_context(self.tenant):
                    query = build_query(handler)
                    node_capacity = NodeCapacity(handler._mapper.report_type_map, query, _resolution)
                    node_capacity.populate_dataclass()
                    # build expected values
                    expected_query = query.values(*["usage_start", "node"]).annotate(
                        **node_capacity.capacity_annotations
                    )
                    for row in expected_query:
                        usage_start = str(row.get("usage_start"))
                        node = row.get("node")
                        expected_capacity = row.get("capacity")
                        expected_total_capacity += expected_capacity
                        result_value = node_capacity.capacity_by_date_node.get(usage_start, {}).get(node)
                        self.assertEqual(result_value, expected_capacity)
                    self.assertEqual(expected_total_capacity, node_capacity.capacity_total)
