import datetime
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal

from api.report.ocp.utils.common import _calculate_unused

# Combine the two dataclasses into one dataset.


@dataclass
class NodeCapacitySubset:
    capacity_total: Decimal = Decimal(0)
    capacity_by_usage_node: defaultdict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Decimal)))
    count_total: Decimal = Decimal(0)

    def add_capacity(self, capacity_value, usage_start, node_key):
        """Adds the capacity values for annotations & aggregation."""
        if capacity_value:
            self.capacity_total += capacity_value
            self.capacity_by_usage_node[usage_start][node_key] += capacity_value

    def add_count(self, count_value):
        """Adds the count values together for total aggregation"""
        self.count_total += count_value


class NodeCapacity:
    def __init__(self, report_type_map, query, resolution):
        self.report_type_map = report_type_map
        self.query = query
        self.resolution = resolution
        self._capacity = NodeCapacitySubset()

    @property
    def capacity_annotations(self):
        return self.report_type_map.get("capacity_aggregate", {}).get("node")

    @property
    def count_units(self):
        return self.report_type_map.get("count_units_key")

    def resolution_usage_converter(self, usage_start):
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
            usage_start = self.resolution_usage_converter(entry.get("usage_start", ""))
            cap_value = entry.get(cap_key, 0)
            self._capacity.add_capacity(cap_value, usage_start, node_key)
            self._capacity.add_count(entry.get("capacity_count", 0))

    def _check_provider_map(self, _update_mapping):
        """
        This method allows us to control which values should be
        updated in the row based off the provider map.
        """
        # - drop capacity for the volumes endpoint (because its already summed)
        update_mapping = {}
        keep_keys = set(_update_mapping).intersection(self.capacity_annotations.keys())
        for key in keep_keys:
            update_mapping[key] = _update_mapping.get(key)
        return update_mapping

    def _retrieve_values_from_dataset(self, row):
        """Generates the update update_mapping"""
        update_mapping = {"capacity_count_units": self.count_units}
        update_mapping["capacity"] = self._capacity.capacity_by_usage_node.get(row.get("date"), {}).get(
            row.get("node"), Decimal(0)
        )
        return self._check_provider_map(update_mapping)

    def update_row(self, row, _):
        update_mapping = self._retrieve_values_from_dataset(row)
        _calculate_unused(row, update_mapping)

    def generate_query_sum(self):
        """
        Returns the values that should be added to the meta total.
        """
        return {
            "capacity": self._capacity.capacity_total,
            "capacity_count": self._capacity.count_total,
            "capacity_count_units": self.count_units,
        }
