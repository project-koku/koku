#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import datetime
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal

from django.db.models.query import QuerySet

from api.report.ocp.utils import _calculate_unused


@dataclass
class NodeCapacity:
    """
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
    capacity_by_usage_node: defaultdict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Decimal)))
    count_total: Decimal = Decimal(0)

    @property
    def capacity_annotations(self):
        return self.report_type_map.get("capacity_dataclass", {}).get("node")

    @property
    def count_units(self):
        return self.report_type_map.get("count_units_key")

    def _add_capacity(self, capacity_value, usage_start, node_key):
        """Adds the capacity values for annotations & aggregation."""
        if capacity_value:
            self.capacity_total += capacity_value
            self.capacity_by_usage_node[usage_start][node_key] += capacity_value

    def _add_count(self, count_value):
        """Adds the count values together for total aggregation"""
        self.count_total += count_value

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
        cap_data = self.query.values(*["usage_start", "node"]).annotate(**self.capacity_annotations)
        for entry in cap_data:
            node_key = entry.get("node", "")
            usage_start = self._resolution_usage_converter(entry.get("usage_start", ""))
            cap_value = entry.get(cap_key, 0)
            self._add_capacity(cap_value, usage_start, node_key)
            self._add_count(entry.get("capacity_count", 0))

    def _finalize_mapping(self, dataset_mapping):
        """
        This method controls the logic to decide which keys
        from the dataset that should be updated or added
        in the row.

        Currently we only accept keys found in the capacity dataclass.
        """
        # We are using this logic to not update the capacity for
        # the volume endpoints since it is already summed.
        finalized_mapping = {}
        keep_keys = set(dataset_mapping).intersection(self.capacity_annotations.keys())
        keep_keys.add("capacity_count_units")
        for key in keep_keys:
            finalized_mapping[key] = dataset_mapping.get(key)
        return finalized_mapping

    def _retrieve_all_values(self, row):
        """Generates a mapping of values that need to be updated."""
        update_mapping = {"capacity_count_units": self.count_units}
        update_mapping["capacity"] = self.capacity_by_usage_node.get(row.get("date"), {}).get(
            row.get("node"), Decimal(0)
        )
        return update_mapping

    def update_row(self, row, _):
        finalized_mapping = self._finalize_mapping(self._retrieve_all_values(row))
        _calculate_unused(row, finalized_mapping)

    def generate_query_sum(self):
        """
        Returns the values that should be added to the meta total.
        """
        return {
            "capacity": self.capacity_total,
            "capacity_count": self.count_total,
            "capacity_count_units": self.count_units,
        }
