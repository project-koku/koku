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

from api.report.ocp.utils import calculate_unused


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
    def count_annotations(self):
        return self.capacity_aggregate.get("cluster_instance_counts", {})

    def __post_init__(self):
        self._populate_count_values()

    def _populate_count_values(self):
        """
        Queries for the node instance counts, then iterates over the values to
        aggregate our different resolution variants for our time scope options.
        """
        if not self.count_annotations:
            # Short circuit for if the count annotations is
            # not present in the provider map
            return False
        node_instance_counts = self.query.values(*["usage_start", "node"]).annotate(**self.count_annotations)
        for cluster_to_node in node_instance_counts:
            cluster = cluster_to_node.get("cluster")
            usage_key = self._resolution_usage_converter(cluster_to_node.get("usage_start"))
            capacity_count = cluster_to_node.get("capacity_count")
            self._add_count(capacity_count, usage_key, cluster)
        return True

    def _add_capacity(self, cap_value, usage_start, cluster_key):
        """Adds the capacity value to to all capacity resolution variants."""
        if cap_value:
            self.capacity_total += cap_value
            self.capacity_by_cluster[cluster_key] += cap_value
            self.capacity_by_date[usage_start] += cap_value
            self.capacity_by_date_cluster[usage_start][cluster_key] += cap_value

    def _add_count(self, cluster_mapping_value, usage_start, cluster_key):
        """Adds the count value to all count resolution variants."""
        if cluster_mapping_value:
            self.count_total += cluster_mapping_value
            self.count_by_date_cluster[usage_start][cluster_key] += cluster_mapping_value
            self.count_by_date[usage_start] += cluster_mapping_value
            self.count_by_cluster[cluster_key] += cluster_mapping_value

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
