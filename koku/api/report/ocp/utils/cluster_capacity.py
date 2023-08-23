import datetime
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from functools import cached_property

from api.report.ocp.utils.common import _calculate_unused


# TODO (cody): Figure out if I could combine these two classes into one.
# Potentially, duck typing this class with the Node capacity.


@dataclass
class ClusterCapacitySubsets:
    """ """

    capacity_total: Decimal = Decimal(0)
    capacity_by_usage: defaultdict = field(default_factory=lambda: defaultdict(Decimal))  # resolution_total:
    capacity_by_usage_cluster: defaultdict = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(Decimal))
    )  # resolution_level_total
    capacity_by_cluster: defaultdict = field(default_factory=lambda: defaultdict(Decimal))  # by_level
    count_total: Decimal = Decimal(0)
    count_by_usage: defaultdict = field(default_factory=lambda: defaultdict(Decimal))
    count_by_usage_cluster: defaultdict = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(Decimal))
    )  # count_by_usage_level
    count_by_cluster: defaultdict = field(default_factory=lambda: defaultdict(Decimal))

    def add_capacity(self, cap_value, usage_start, level_value):
        """Adds the capacity value to to all capacity aggregrations."""
        if cap_value:
            self.capacity_total += cap_value
            self.capacity_by_cluster[level_value] += cap_value
            self.capacity_by_usage[usage_start] += cap_value
            self.capacity_by_usage_cluster[usage_start][level_value] += cap_value

    def add_count(self, cluster_mapping_value, usage_start, cluster_key):
        """adds the count values together."""
        self.count_total += cluster_mapping_value
        self.count_by_usage_cluster[usage_start][cluster_key] += cluster_mapping_value
        self.count_by_usage[usage_start] += cluster_mapping_value
        self.count_by_cluster[cluster_key] += cluster_mapping_value


class ClusterCapacity:
    def __init__(self, report_type_map, query, resolution):
        self.report_type_map = report_type_map
        self.query = query
        self.resolution = resolution
        self._capacity = ClusterCapacitySubsets()

    @property
    def capacity_annotations(self):
        return self.report_type_map.get("capacity_aggregate", {}).get("cluster")

    @property
    def count_units(self):
        return self.report_type_map.get("count_units_key")

    @cached_property
    def cluster_count_mapping(self):
        """
        Creates a mapping of cluster to node instance counts. This is only
        used to create the instance counts for the cluster level view.

        Mapping Layout:
        {usage_key: {cluster: sum(node_instance_count)}}

        usage_key: str(date) ex. "2023-08-22"
        cluster: Coalesce("cluster_alias", "cluster_id")
        node_instance_count: max(instance column)
        """
        count_annotations = self.report_type_map.get("capacity_aggregate", {}).get("cluster_instance_counts")
        if not count_annotations:
            return {}
        cluster_capacity_vals = self.query.values(*["usage_start", "node"]).annotate(**count_annotations)
        cluster_mapping = {}
        for cluster_to_node in cluster_capacity_vals:
            cluster = cluster_to_node.get("cluster")
            usage_key = self.resolution_usage_converter(cluster_to_node.get("usage_start"))
            capacity_count = cluster_to_node.get("capacity_count")

            if usage_mapping := cluster_mapping.get(cluster):
                current_capacity_count = 0
                if mapping_count := usage_mapping.get(usage_key):
                    current_capacity_count = mapping_count
                usage_mapping[usage_key] = current_capacity_count + capacity_count
            else:
                cluster_mapping[cluster] = {usage_key: capacity_count}
        return cluster_mapping

    def resolution_usage_converter(self, usage_start):
        """Converts the usage data in to the correct key based on resolution."""
        if self.resolution == "daily" and isinstance(usage_start, datetime.date):
            usage_start = usage_start.isoformat()
        if self.resolution == "monthly":
            usage_start = usage_start.strftime("%Y-%m")
        return usage_start

    def populate_dataclass(self):
        """
        Retrieves data to populates the capacity dataclass.
        """
        if not self.capacity_annotations:
            return None
        cap_key = list(self.capacity_annotations.keys())[0]
        cap_data = self.query.values(*["usage_start", "cluster_id"]).annotate(**self.capacity_annotations)
        for entry in cap_data:
            cluster_key = entry.get("cluster", "")
            if cluster_key:
                usage_start = self.resolution_usage_converter(entry.get("usage_start", ""))
                cap_value = entry.get(cap_key, 0)
                self._capacity.add_capacity(cap_value, usage_start, cluster_key)
                cluster_mapping_value = self.cluster_count_mapping.get(cluster_key, {}).get(usage_start)
                self._capacity.add_count(cluster_mapping_value, usage_start, cluster_key)

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

    def _retrieve_values_from_dataset(self, row, start_date_param):
        """Generates the update mapping"""
        update_mapping = {"capacity_count_units": self.count_units}
        cluster_list = row.get("clusters")
        if self.resolution == "monthly" and not start_date_param:
            if cluster_list:
                update_mapping["capacity"] = sum(
                    [self._capacity.capacity_by_cluster.get(cluster_id, Decimal(0)) for cluster_id in cluster_list]
                )
                update_mapping["capacity_count"] = sum(
                    [self._capacity.count_by_cluster.get(cluster_id, Decimal(0)) for cluster_id in cluster_list]
                )
                return update_mapping
            update_mapping["capacity"] = self._capacity.capacity_total
            update_mapping["capacity_count"] = self._capacity.count_total
            return update_mapping
        row_date = row.get("date")
        if cluster_list:
            update_mapping["capacity"] = sum(
                [
                    self._capacity.capacity_by_usage_cluster.get(row_date, {}).get(cluster_id, Decimal(0))
                    for cluster_id in cluster_list
                ]
            )
            update_mapping["capacity_count"] = sum(
                [
                    self._capacity.count_by_usage_cluster.get(row_date, {}).get(cluster_id, Decimal(0))
                    for cluster_id in cluster_list
                ]
            )
            return update_mapping
        else:
            update_mapping["capacity"] = self._capacity.capacity_by_usage.get(row_date, Decimal(0))
            update_mapping["capacity_count"] = self._capacity.count_by_usage.get(row_date, Decimal(0))
        return update_mapping

    def update_row(self, row, start_date_param):
        """Modify the rows"""
        update_mapping = self._check_provider_map(self._retrieve_values_from_dataset(row, start_date_param))
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
