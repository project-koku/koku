#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Dataclass used to calculate cluster capacity."""
import datetime
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal

from django.db.models.query import QuerySet


# Developer Note:
# This is common code used in the
# query handler and node capacity.
def calculate_unused(row, finalized_mapping=None):
    """Calculates the unused portions of the capacity & request."""
    # Populate unused request and capacity
    finalized_mapping = finalized_mapping or {}
    for key, value in finalized_mapping.items():
        row[key] = value
    capacity = row.get("capacity", Decimal(0))
    if not capacity:
        capacity = Decimal(0)
    usage = row.get("usage") if row.get("usage") else Decimal(0)
    request = row.get("request") if row.get("request") else Decimal(0)
    effective_usage = max(usage, request)
    unused_capacity = max(capacity - effective_usage, 0)
    if capacity <= 0:
        # Check to see if we are about to divide by zero or a negative.
        capacity = max(capacity, Decimal(1))
    capacity_unused_percent = (unused_capacity / capacity) * 100
    row["capacity_unused"] = unused_capacity
    row["capacity_unused_percent"] = capacity_unused_percent
    unused_request = max(request - usage, 0)
    row["request_unused"] = unused_request
    if request <= 0:
        request = 1
    row["request_unused_percent"] = (unused_request / capacity) * 100


@dataclass
class ClusterCapacity:
    """A class to calaculate the cluster capacity.

    Formula:
        capacity: Sum([Max(day0), Max(day1)])
        count: Sum(node instance counts in cluster)

    Due to our different resolutions this dataclass generates
    capacity for:
      report_type_map:    provider_map report type
      query:              django base query
      resolution:         resolution provider by request
      *_total:            overall total over time period
      *_by_date:         overall sum for given time range
      *_by_date_cluster: overall sum per cluster per day
      *_by_cluster:       overall sum per cluster
    """

    report_type_map: defaultdict
    query: QuerySet
    resolution: str
    capacity_total: Decimal = Decimal(0)
    capacity_by_date: defaultdict = field(default_factory=lambda: defaultdict(Decimal))
    capacity_by_date_cluster: defaultdict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Decimal)))
    capacity_by_cluster: defaultdict = field(default_factory=lambda: defaultdict(Decimal))
    count_total: Decimal = Decimal(0)
    count_by_date: defaultdict = field(default_factory=lambda: defaultdict(Decimal))
    count_by_date_cluster: defaultdict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Decimal)))
    count_by_cluster: defaultdict = field(default_factory=lambda: defaultdict(Decimal))

    @property
    def capacity_aggregate(self):
        return self.report_type_map.get("capacity_aggregate", {})

    @property
    def capacity_annotations(self):
        return self.capacity_aggregate.get("cluster", {})

    @property
    def count_units(self):
        return self.report_type_map.get("count_units_key")

    @property
    def capacity_count_key(self):
        return self.report_type_map.get("capacity_count_key")

    @property
    def count_annotations(self):
        return self.capacity_aggregate.get("cluster_instance_counts", {})

    def __post_init__(self):
        self._populate_count_values()

    def _aggregate_capacity_count_by_cluster(self, node_instance_counts):
        """
        Helper function to aggregate capacity count by cluster.

        Aggregates the maximum capacity count for each node within a cluster from a given set of node instances.

        Args:
            node_instance_counts (QuerySet): Django queryset containing annotated node instance counts
                                                with cluster, node, usage_start and capacity_count fields.

        Side effects:
            - Modifies `self.count_by_cluster` to include the total capacity count for each cluster keyed by cluster.

            - Also updates `self.count_total` to include the total aggregated capacity for all clusters.

        """

        unique_cluster_node_counts = defaultdict(lambda: defaultdict(Decimal))
        for count in node_instance_counts:
            cluster, node, capacity_count = (count["cluster"], count["node"], count["capacity_count"])

            # count each node per cluster once
            # use max capacity count if a node has multiple values
            unique_cluster_node_counts[cluster][node] = max(
                capacity_count, unique_cluster_node_counts[cluster].get(node, 0)
            )

        for cluster in unique_cluster_node_counts:
            self.count_by_cluster[cluster] = sum(unique_cluster_node_counts.get(cluster).values())

        # sum capacity count for all clusters
        self.count_total = sum(self.count_by_cluster.values())

    def _aggregate_capacity_count_by_date(self, node_instance_counts):
        """
        Aggregates the maximu capacity count for each node within a cluster for each date
        from a given set of node instances.

        Args:
            node_instance_counts (QuerySet): Django queryset containing annotated node instance counts
                                                with cluster, node, usage_start and capacity_count fields.

        Side effects:
            - Modifies `self.count_by_date_cluster` to include the total capacity count for each cluster
              on each date, keyed by date and then cluster.

            - Also updates `self.count_by_date` to include the total aggregated capacity
              for each date across all clusters.
        """

        daily_max_node_capacities = defaultdict(lambda: defaultdict(Decimal))
        for count in node_instance_counts:
            cluster, node, usage_start, capacity_count = (
                count["cluster"],
                count["node"],
                count["usage_start"],
                count["capacity_count"],
            )
            # count each node per cluster per date once
            # use max capacity count if a node has multiple values
            usage_start_resolution = self._resolution_usage_converter(usage_start)

            # composite key to access daily_max_node_capacities dict
            cluster_date_key = (cluster, usage_start_resolution)
            daily_max_node_capacities[cluster_date_key][node] = max(
                capacity_count, daily_max_node_capacities[cluster_date_key].get(node, 0)
            )

        for (cluster, date), nodes in daily_max_node_capacities.items():
            self.count_by_date_cluster[date][cluster] = sum(nodes.values())
            self.count_by_date[date] = self.count_by_date.get(date, 0) + sum(nodes.values())

    def _populate_count_values(self):
        """
        Consolidates and aggregates node instance count data based on various resolution variants

        Returns:
            bool: True if count annotations exist and the aggregations process is completed,
                  otherwise False
        """
        if not self.count_annotations:
            return False

        node_instance_counts = (
            self.query.values(*["usage_start", "node"]).annotate(**self.count_annotations).filter(node__isnull=False)
        )

        self._aggregate_capacity_count_by_cluster(node_instance_counts)
        self._aggregate_capacity_count_by_date(node_instance_counts)

        return True

    def _add_capacity(self, cap_value, usage_start, cluster_key):
        """Adds the capacity value to to all capacity resolution variants."""
        if cap_value:
            self.capacity_total += cap_value
            self.capacity_by_cluster[cluster_key] += cap_value
            self.capacity_by_date[usage_start] += cap_value
            self.capacity_by_date_cluster[usage_start][cluster_key] += cap_value

    def _resolution_usage_converter(self, usage_start):
        """Normalizes the usage_start based on the resolution provided."""
        if self.resolution == "daily" and isinstance(usage_start, datetime.date):
            usage_start = usage_start.isoformat()
        if self.resolution == "monthly":
            usage_start = usage_start.strftime("%Y-%m")
        return usage_start

    def populate_dataclass(self):
        """
        Retrieves data to populates the capacity resolution variants.
        """
        if not self.capacity_annotations:
            # Short circuit for if the capacity annotations is
            # not present in the provider map.
            return False
        cap_key = list(self.capacity_annotations.keys())[0]
        cap_data = self.query.values(*["usage_start", "cluster_id"]).annotate(**self.capacity_annotations)
        for entry in cap_data:
            cluster_key = entry.get("cluster", "")
            if cluster_key:
                usage_start = self._resolution_usage_converter(entry.get("usage_start", ""))
                cap_value = entry.get(cap_key, 0)
                self._add_capacity(cap_value, usage_start, cluster_key)

    def _finalize_mapping(self, dataset_mapping):
        """
        Logic to decide which keys to update in the row,
        based off of the keys are present in the
        report type provider map.

        For example, we do not want to overwrite capacity for
        the volume endpoint, because it is already summed.
        """
        # We are using this logic to not update the capacity for
        # the volume endpoints since it is already summed.
        finalized_mapping = {}
        annotations_keys = set(self.count_annotations.keys()).union(self.capacity_annotations.keys())
        keep_keys = set(dataset_mapping).intersection(annotations_keys)
        if "capacity_count" in keep_keys:
            keep_keys.add("capacity_count_units")
        for key in keep_keys:
            finalized_mapping[key] = dataset_mapping.get(key)
        return finalized_mapping

    def _generate_resolution_values(self, row, start_date_param):
        """
        Determines which capacity and count to use based off the resolution
        and start date parameter. If multiple clusters are found it will sum
        the count and capacity values for each cluster present for an overall
        total.
        """
        update_mapping = {"capacity_count_units": self.count_units}
        cluster_list = row.get("clusters")
        if self.resolution == "monthly" and not start_date_param:
            if cluster_list:
                update_mapping["capacity"] = sum(
                    [self.capacity_by_cluster.get(cluster_id, Decimal(0)) for cluster_id in cluster_list]
                )
                update_mapping["capacity_count"] = sum(
                    [self.count_by_cluster.get(cluster_id, Decimal(0)) for cluster_id in cluster_list]
                )
                return update_mapping
            update_mapping["capacity"] = self.capacity_total
            update_mapping["capacity_count"] = self.count_total
            return update_mapping
        row_date = row.get("date")
        if cluster_list:
            update_mapping["capacity"] = sum(
                [
                    self.capacity_by_date_cluster.get(row_date, {}).get(cluster_id, Decimal(0))
                    for cluster_id in cluster_list
                ]
            )
            update_mapping["capacity_count"] = sum(
                [
                    self.count_by_date_cluster.get(row_date, {}).get(cluster_id, Decimal(0))
                    for cluster_id in cluster_list
                ]
            )
            return update_mapping
        else:
            update_mapping["capacity"] = self.capacity_by_date.get(row_date, Decimal(0))
            update_mapping["capacity_count"] = self.count_by_date.get(row_date, Decimal(0))
        return update_mapping

    def update_row(self, row, start_date_param):
        """Modify the rows"""
        finalized_mapping = self._finalize_mapping(self._generate_resolution_values(row, start_date_param))
        calculate_unused(row, finalized_mapping)

    def generate_query_sum(self):
        """
        Returns the values that should be added to the meta total.
        """
        query_sum = {"capacity_count_units": self.count_units}
        if self.capacity_annotations:
            query_sum["capacity"] = self.capacity_total
        if self.count_annotations:
            query_sum["capacity_count"] = self.count_total
        return query_sum
