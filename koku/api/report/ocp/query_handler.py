#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Query Handling for Reports."""
import copy
import datetime
import logging
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from decimal import DivisionByZero
from decimal import InvalidOperation
from functools import cached_property

from django.db.models import Case
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Coalesce
from django_tenants.utils import tenant_context

from api.models import Provider
from api.report.ocp.provider_map import OCPProviderMap
from api.report.queries import is_grouped_by_node
from api.report.queries import is_grouped_by_project
from api.report.queries import ReportQueryHandler
from cost_models.models import CostModel
from cost_models.models import CostModelMap

LOG = logging.getLogger(__name__)


@dataclass
class CapacitySubsets:
    key: str
    level_key: str
    resolution: str
    total: Decimal = Decimal(0)
    resolution_total: defaultdict = field(default_factory=lambda: defaultdict(Decimal))
    resolution_level_total: defaultdict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Decimal)))
    by_level: defaultdict = field(default_factory=lambda: defaultdict(Decimal))

    def add(self, cap_value, usage_start, level_value):
        self.total += cap_value
        if self.resolution == "daily":
            if isinstance(usage_start, datetime.date):
                usage_start = usage_start.isoformat()
            self.by_level[level_value] += cap_value
            self.resolution_level_total[usage_start][level_value] += cap_value
            self.resolution_total[usage_start] += cap_value
        elif self.resolution == "monthly":
            month = usage_start.month
            self.by_level[level_value] += cap_value
            self.resolution_total[month] += cap_value
            self.resolution_level_total[month][level_value] += cap_value


def _calculate_unused(row):
    """Calculates the unused portions of the capacity & request."""
    # Populate unused request and capacity
    capacity = row.get("capacity", Decimal(0))
    if capacity <= 0:
        capacity = 1  # prevents dividing by zero
    usage = row.get("usage", 0)
    request = row.get("request", 0)
    effective_usage = max(usage, request)
    unused_capacity = max(capacity - effective_usage, 0)
    capacity_unused_percent = (unused_capacity / capacity) * 100
    row["capacity_unused"] = unused_capacity
    row["capacity_unused_percent"] = capacity_unused_percent
    unused_request = max(request - usage, 0)
    row["request_unused"] = unused_request
    if request <= 0:
        request = 1
    row["request_unused_percent"] = unused_request / request * 100


class OCPReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for OCP."""

    provider = Provider.PROVIDER_OCP

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        mapper_class = OCPProviderMap
        self._limit = parameters.get_filter("limit")
        self._report_type = parameters.report_type
        # Update which field is used to calculate cost by group by param.
        if is_grouped_by_project(parameters) and parameters.report_type == "costs":
            self._report_type = parameters.report_type + "_by_project"
        self._mapper = mapper_class(provider=self.provider, report_type=self._report_type)
        self.group_by_options = self._mapper.provider_map.get("group_by_options")

        # We need to overwrite the default pack definitions with these
        # Order of the keys matters in how we see it in the views.
        ocp_pack_keys = {
            "infra_raw": {"key": "raw", "group": "infrastructure"},
            "infra_markup": {"key": "markup", "group": "infrastructure"},
            "infra_usage": {"key": "usage", "group": "infrastructure"},
            "infra_distributed": {"key": "distributed", "group": "infrastructure"},
            "infra_total": {"key": "total", "group": "infrastructure"},
            "sup_raw": {"key": "raw", "group": "supplementary"},
            "sup_markup": {"key": "markup", "group": "supplementary"},
            "sup_usage": {"key": "usage", "group": "supplementary"},
            "sup_distributed": {"key": "distributed", "group": "supplementary"},
            "sup_total": {"key": "total", "group": "supplementary"},
            "cost_raw": {"key": "raw", "group": "cost"},
            "cost_markup": {"key": "markup", "group": "cost"},
            "cost_usage": {"key": "usage", "group": "cost"},
            "cost_platform_distributed": {"key": "platform_distributed", "group": "cost"},
            "cost_worker_unallocated_distributed": {"key": "worker_unallocated_distributed", "group": "cost"},
            "cost_total_distributed": {"key": "distributed", "group": "cost"},
            "cost_total": {"key": "total", "group": "cost"},
        }
        ocp_pack_definitions = copy.deepcopy(self._mapper.PACK_DEFINITIONS)
        ocp_pack_definitions["cost_groups"]["keys"] = ocp_pack_keys
        # Note: The value & units will be supplied by the usage keys in the parent class.
        ocp_pack_definitions["unused_usage"] = {
            "keys": {
                "request_unused": {"key": "unused", "group": "request"},
                "request_unused_percent": {"key": "unused_percent", "group": "request"},
                "capacity_unused": {"key": "unused", "group": "capacity"},
                "capacity_unused_percent": {"key": "unused_percent", "group": "capacity"},
                "capacity_count": {"key": "count", "group": "capacity"},
                "capacity_count_units": {"key": "count_units", "group": "capacity"},
            },
            "units": "usage_units",
        }

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
        # super() needs to be called before _get_group_by is called

        self._mapper.PACK_DEFINITIONS = ocp_pack_definitions

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Returns:
            (Dict): query annotations dictionary

        """
        annotations = {
            "date": self.date_trunc("usage_start"),
            # this currency is used by the provider map to populate the correct currency value
            "currency_annotation": Value(self.currency, output_field=CharField()),
            **self.exchange_rate_annotation_dict,
        }
        # { query_param: database_field_name }
        fields = self._mapper.provider_map.get("annotations")
        for q_param, db_field in fields.items():
            annotations[q_param] = F(db_field)
        if is_grouped_by_project(self.parameters):
            if self._category:
                annotations["project"] = Coalesce(F("cost_category__name"), F("namespace"), output_field=CharField())
            else:
                annotations["project"] = F("namespace")

        if is_grouped_by_node(self.parameters):
            if self._mapper.report_type_map.get("capacity_aggregate", {}).get("node"):
                self.report_annotations.update(
                    self._mapper.report_type_map.get("capacity_aggregate", {}).get("node", {})
                )

        return annotations

    @cached_property
    def source_to_currency_map(self):
        """
        OCP sources do not have costs associated, so we need to
        grab the base currency from the cost model, and create
        a mapping of source_uuid to currency.
        returns:
            dict: {source_uuid: currency}
        """
        source_map = defaultdict(lambda: self._mapper.cost_units_fallback)
        cost_models = CostModel.objects.all().values("uuid", "currency").distinct()
        cm_to_currency = {row["uuid"]: row["currency"] for row in cost_models}
        mapping = CostModelMap.objects.all().values("provider_uuid", "cost_model_id")
        source_map |= {row["provider_uuid"]: cm_to_currency[row["cost_model_id"]] for row in mapping}
        return source_map

    @cached_property
    def exchange_rate_annotation_dict(self):
        """Get the exchange rate annotation based on the exchange_rates property."""
        exchange_rate_whens = [
            When(**{"source_uuid": uuid, "then": Value(self.exchange_rates.get(cur, {}).get(self.currency, 1))})
            for uuid, cur in self.source_to_currency_map.items()
        ]
        infra_exchange_rate_whens = [
            When(**{self._mapper.cost_units_key: k, "then": Value(v.get(self.currency))})
            for k, v in self.exchange_rates.items()
        ]
        return {
            "exchange_rate": Case(*exchange_rate_whens, default=1, output_field=DecimalField()),
            "infra_exchange_rate": Case(*infra_exchange_rate_whens, default=1, output_field=DecimalField()),
        }

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = self._initialize_response_output(self.parameters)
        if self._report_type == "costs_by_project":
            # Add a boolean flag for the overhead dropdown in the UI
            with tenant_context(self.tenant):
                output["distributed_overhead"] = False
                if (
                    self.query_table.objects.filter(self.query_filter)
                    .filter(cost_model_rate_type__in=["platform_distributed", "worker_distributed"])
                    .exists()
                ):
                    output["distributed_overhead"] = True
        output["data"] = self.query_data

        self.query_sum = self._pack_data_object(self.query_sum, **self._mapper.PACK_DEFINITIONS)
        output["total"] = self.query_sum

        if self._delta:
            output["delta"] = self.query_delta

        return output

    def execute_query(self):  # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = self.initialize_totals()
        data = []

        with tenant_context(self.tenant):
            query = self.query_table.objects.filter(self.query_filter)
            if self.query_exclusions:
                query = query.exclude(self.query_exclusions)
            query = query.annotate(**self.annotations)
            group_by_value = self._get_group_by()

            query_group_by = ["date"] + group_by_value
            query_order_by = ["-date", self.order]
            query_data = query.values(*query_group_by).annotate(**self.report_annotations)

            if is_grouped_by_project(self.parameters):
                query_data = self._project_classification_annotation(query_data)
            if self._limit and query_data:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            # Populate the 'total' section of the API response
            if query.exists():
                aggregates = self._mapper.report_type_map.get("aggregates")
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            query_data, total_capacity = self.get_capacity(query_data)
            if total_capacity:
                query_sum.update(total_capacity)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            query_data = self.order_by(query_data, query_order_by)

            if self.is_csv_output:
                data = list(query_data)
            else:
                # Pass in a copy of the group by without the added
                # tag column name prefix
                groups = copy.deepcopy(query_group_by)
                groups.remove("date")
                data = self._apply_group_by(list(query_data), groups)
                data = self._transform_data(query_group_by, 0, data)

        sum_init = {"cost_units": self.currency}
        if self._mapper.usage_units_key:
            sum_init["usage_units"] = self._mapper.usage_units_key
        query_sum.update(sum_init)

        ordered_total = {
            total_key: query_sum[total_key] for total_key in self.report_annotations.keys() if total_key in query_sum
        }
        ordered_total.update(query_sum)

        self.query_sum = ordered_total
        self.query_data = data
        return self._format_query_response()

    def get_capacity(self, query_data):  # noqa: C901
        """Calculate cluster capacity for all nodes over the date range."""
        if is_grouped_by_node(self.parameters):
            annotations = self._mapper.report_type_map.get("capacity_aggregate", {}).get("node")
            if annotations:
                capacity_sets = self._generate_capacity_subsets(annotations, "node", ["usage_start", "node"])
                return self._get_node_capacity(query_data, capacity_sets)
        else:
            annotations = self._mapper.report_type_map.get("capacity_aggregate", {}).get("cluster")
            if annotations:
                annotations["cluster"] = Coalesce("cluster_alias", "cluster_id")
                capacity_sets = self._generate_capacity_subsets(annotations, "cluster", ["usage_start", "cluster_id"])
                return self._get_cluster_capacity(query_data, capacity_sets)
        return query_data, {}

    def _generate_capacity_subsets(self, annotations, level_key, group_list):
        """Calculate capacity over the date range"""
        cap_key = list(annotations.keys())[0]
        _capacity = CapacitySubsets(key=cap_key, level_key=level_key, resolution=self.resolution)
        q_table = self._mapper.query_table
        LOG.debug(f"Using query table: {q_table}")
        query = q_table.objects.filter(self.query_filter)
        if self.query_exclusions:
            query = query.exclude(self.query_exclusions)
        with tenant_context(self.tenant):
            cap_data = query.values(*group_list).annotate(**annotations)
            for entry in cap_data:
                level_value = entry.get(level_key, "")
                usage_start = entry.get("usage_start", "")
                cap_value = entry.get(cap_key, 0)
                if cap_value is None:
                    cap_value = 0
                _capacity.add(cap_value, usage_start, level_value)
        return _capacity

    def _get_node_capacity(self, query_data, _capacity):
        """Calculate node capacity for all nodes over the date range."""
        for row in query_data:
            if row.get("node"):
                _calculate_unused(row)
            elif self.resolution == "daily":
                row[_capacity.key] = _capacity.resolution_total.get(row.get("date"), Decimal(0))
            elif self.resolution == "monthly" and not self.parameters.get("start_date"):
                row[_capacity.key] = _capacity.total
            else:
                row_date = datetime.datetime.strptime(row.get("date"), "%Y-%m").month
                row[_capacity.key] = _capacity.resolution_total.get(row_date, Decimal(0))
        return query_data, {_capacity.key: _capacity.total}

    def _get_cluster_capacity(self, query_data, _capacity):
        """Calculate the cluster capacity."""
        for row in query_data:
            cluster_list = row.get("clusters")
            if self.resolution == "monthly" and not self.parameters.get("start_date"):
                if cluster_list:
                    row[_capacity.key] = sum(
                        [_capacity.by_level.get(cluster_id, Decimal(0)) for cluster_id in cluster_list]
                    )
                else:
                    row[_capacity.key] = _capacity.total
            else:
                row_date = row.get("date")
                if self.resolution == "monthly":
                    row_date = datetime.datetime.strptime(row.get("date"), "%Y-%m").month
                if cluster_list:
                    row[_capacity.key] = sum(
                        [
                            _capacity.resolution_level_total.get(row_date, {}).get(cluster_id, Decimal(0))
                            for cluster_id in cluster_list
                        ]
                    )
                else:
                    row[_capacity.key] = _capacity.resolution_total.get(row_date, Decimal(0))
            _calculate_unused(row)
        return query_data, {_capacity.key: _capacity.total}

    def add_deltas(self, query_data, query_sum):
        """Calculate and add cost deltas to a result set.

        Args:
            query_data (list) The existing query data from execute_query
            query_sum (list) The sum returned by calculate_totals

        Returns:
            (dict) query data with new with keys "value" and "percent"

        """
        if "__" in self._delta:
            return self.add_current_month_deltas(query_data, query_sum)
        else:
            return super().add_deltas(query_data, query_sum)

    def add_current_month_deltas(self, query_data, query_sum):
        """Add delta to the resultset using current month comparisons."""
        delta_field_one, delta_field_two = self._delta.split("__")

        for row in query_data:
            delta_value = Decimal(row.get(delta_field_one) or 0) - Decimal(row.get(delta_field_two) or 0)

            row["delta_value"] = delta_value
            try:
                row["delta_percent"] = (
                    Decimal(row.get(delta_field_one) or 0) / Decimal(row.get(delta_field_two) or 0) * Decimal(100)
                )
            except (DivisionByZero, ZeroDivisionError, InvalidOperation):
                row["delta_percent"] = None

        total_delta = Decimal(query_sum.get(delta_field_one) or 0) - Decimal(query_sum.get(delta_field_two) or 0)
        try:
            total_delta_percent = (
                Decimal(query_sum.get(delta_field_one) or 0)
                / Decimal(query_sum.get(delta_field_two) or 0)
                * Decimal(100)
            )
        except (DivisionByZero, ZeroDivisionError, InvalidOperation):
            total_delta_percent = None

        self.query_delta = {"value": total_delta, "percent": total_delta_percent}

        return query_data
