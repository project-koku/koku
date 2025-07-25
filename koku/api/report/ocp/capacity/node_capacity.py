#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Dataclass used to calculate node capacity."""
import datetime
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal

from django.db.models.query import QuerySet

from api.report.ocp.capacity.cluster_capacity import calculate_unused


@dataclass
class NodeCapacity:
    """
    A class to calaculate the node capacity.

    report_type_map:        provider_map report type
    query:                  django base query
    resolution:             resolution provider by request
    -- Calaculated during populate dataclass --
    capacity_total:         total capacity count
    capacity_usage_by_node: capacity total by usage date and node
    count_total:            total instance count
    """

    report_type_map: defaultdict
    query: QuerySet
    resolution: str
    capacity_total: Decimal = Decimal(0)
    capacity_by_date_node: defaultdict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Decimal)))
    count_total: Decimal = Decimal(0)

    @property
    def capacity_aggregate(self):
        return self.report_type_map.get("capacity_aggregate", {})

    @property
    def capacity_annotations(self):
        return self.capacity_aggregate.get("node", {})

    @property
    def count_units(self):
        return self.report_type_map.get("count_units_key")

    def _add_capacity(self, capacity_value, usage_start, node_key):
        """Adds the capacity values for annotations & aggregation."""
        if capacity_value:
            self.capacity_total += capacity_value
            self.capacity_by_date_node[usage_start][node_key] += capacity_value

    def _resolution_usage_converter(self, usage_start):
        """Converts the usage data in to the correct key based on resolution."""
        if self.resolution == "daily" and isinstance(usage_start, datetime.date):
            usage_start = usage_start.isoformat()
        if self.resolution == "monthly":
            usage_start = usage_start.strftime("%Y-%m")
        return usage_start

    def populate_dataclass(self):
        """
        Creates and populates the capacity dataclass.
        """
        cap_key = list(self.capacity_annotations.keys())[0]
        node_capacity_counts = (
            self.query.values(*["usage_start", "node"])
            .annotate(**self.capacity_annotations)
            .filter(node__isnull=False)
        )

        # Count each node once. Use max capacity count if a node has multiple values

        unique_nodes = defaultdict(Decimal)
        for entry in node_capacity_counts:
            node = entry.get("node", "")
            capacity_count = entry.get("capacity_count", 0)
            usage_start = self._resolution_usage_converter(entry.get("usage_start", ""))
            cap_value = entry.get(cap_key, 0)
            self._add_capacity(cap_value, usage_start, node)

            unique_nodes[node] = max(capacity_count, unique_nodes.get(node, 0))

        # Aggregate total node capacity count
        self.count_total = sum(unique_nodes.values())

    def _finalize_mapping(self, dataset_mapping):
        """
        Logic to decide which keys to update in the row,
        based off of the keys are present in the
        report type provider map.

        For example, we do not want to overwrite capacity for
        the volume endpoint, because it is already summed.
        """
        finalized_mapping = {}
        keep_keys = set(dataset_mapping).intersection(self.capacity_annotations.keys())
        if "capacity_count" in keep_keys:
            keep_keys.add("capacity_count_units")
        for key in keep_keys:
            finalized_mapping[key] = dataset_mapping.get(key)
        return finalized_mapping

    def update_row(self, row, _):
        """Updates the row with the capacity aggregation.

        Developers Note:
        We are garunteed to be group by node, which eliminates
        alot of the complexities we see for cluster capacity.
        """
        update_mapping = {"capacity_count_units": self.count_units}
        update_mapping["capacity"] = self.capacity_by_date_node.get(row.get("date"), {}).get(
            row.get("node"), Decimal(0)
        )
        calculate_unused(row, self._finalize_mapping(update_mapping))

    def generate_query_sum(self):
        """
        Returns the values that should be added to the meta total.
        """
        return {
            "capacity": self.capacity_total,
            "capacity_count": self.count_total,
            "capacity_count_units": self.count_units,
        }
