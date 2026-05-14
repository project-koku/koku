#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Query Handling for Reports."""
import copy
import logging
from collections import defaultdict
from decimal import Decimal
from decimal import DivisionByZero
from decimal import InvalidOperation
from functools import cached_property

from django.db.models import Case
from django.db.models import CharField
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Sum
from django.db.models import Value
from django.db.models import When
from django.db.models.fields.json import KT
from django.db.models.functions import Coalesce
from django.db.models.functions import Greatest
from django.db.models.functions.comparison import NullIf
from django_tenants.utils import tenant_context

from api.metrics.constants import OCP_METRIC_CPU_CORE_EFFECTIVE_USAGE_HOUR
from api.metrics.constants import OCP_METRIC_CPU_CORE_REQUEST_HOUR
from api.metrics.constants import OCP_METRIC_CPU_CORE_USAGE_HOUR
from api.metrics.constants import OCP_METRIC_MEM_GB_EFFECTIVE_USAGE_HOUR
from api.metrics.constants import OCP_METRIC_MEM_GB_REQUEST_HOUR
from api.metrics.constants import OCP_METRIC_MEM_GB_USAGE_HOUR
from api.models import Provider
from api.report.ocp.capacity.cluster_capacity import calculate_unused
from api.report.ocp.capacity.cluster_capacity import ClusterCapacity
from api.report.ocp.capacity.node_capacity import NodeCapacity
from api.report.ocp.provider_map import OCPProviderMap
from api.report.queries import is_grouped_by_node
from api.report.queries import is_grouped_by_project
from api.report.queries import ReportQueryHandler
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from reporting.models import OCPUsageLineItemDailySummary

LOG = logging.getLogger(__name__)


class OCPReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for OCP."""

    provider = Provider.PROVIDER_OCP

    _CPU_HOUR_METRICS = frozenset(
        {OCP_METRIC_CPU_CORE_USAGE_HOUR, OCP_METRIC_CPU_CORE_REQUEST_HOUR, OCP_METRIC_CPU_CORE_EFFECTIVE_USAGE_HOUR}
    )
    _MEM_HOUR_METRICS = frozenset(
        {OCP_METRIC_MEM_GB_USAGE_HOUR, OCP_METRIC_MEM_GB_REQUEST_HOUR, OCP_METRIC_MEM_GB_EFFECTIVE_USAGE_HOUR}
    )
    _SENTINEL_NAMESPACES = frozenset(
        ["Worker unallocated", "Platform unallocated", "Network unattributed", "Storage unattributed"]
    )

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
        self._mapper = mapper_class(
            provider=self.provider, report_type=self._report_type, schema_name=parameters.tenant.schema_name
        )
        self.group_by_options = self._mapper.report_type_map.get("group_by_options") or self._mapper.provider_map.get(
            "group_by_options"
        )

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
            "cost_network_unattributed_distributed": {"key": "network_unattributed_distributed", "group": "cost"},
            "cost_storage_unattributed_distributed": {"key": "storage_unattributed_distributed", "group": "cost"},
            "cost_gpu_unallocated_distributed": {"key": "gpu_unallocated_distributed", "group": "cost"},
            "cost_total_distributed": {"key": "distributed", "group": "cost"},
            "cost_total": {"key": "total", "group": "cost"},
        }
        ocp_pack_definitions = copy.deepcopy(self._mapper.PACK_DEFINITIONS)
        ocp_pack_definitions["cost_groups"]["keys"] = ocp_pack_keys
        ocp_pack_definitions["request_cpu"] = {"keys": ["request_cpu"], "units": "request_cpu_units"}
        ocp_pack_definitions["request_memory"] = {"keys": ["request_memory"], "units": "request_memory_units"}
        ocp_pack_definitions["request"] = {
            "keys": {
                "request_cpu": {"key": "cpu", "group": "request"},
                "request_memory": {"key": "memory", "group": "request"},
            },
            "units": "usage_units",
        }
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
        ocp_pack_definitions["usage"]["keys"].extend(["data_transfer_in", "data_transfer_out"])
        ocp_pack_definitions["gpu_memory"] = {"keys": ["gpu_memory"], "units": "gpu_memory_units"}
        ocp_pack_definitions["compute"] = {"keys": ["compute"], "units": "mig_compute_units"}
        ocp_pack_definitions["memory"] = {"keys": ["memory"], "units": "mig_memory_units"}
        ocp_pack_definitions["gpu_count"] = {"keys": ["gpu_count"], "units": "gpu_count_units"}

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
            # Skip gpu_count here for GPU report
            if self._report_type == "gpu" and q_param == "gpu_count":
                continue
            annotations[q_param] = F(db_field)
        if is_grouped_by_project(self.parameters):
            if self._category:
                annotations["project"] = Coalesce(F("cost_category__name"), F("namespace"), output_field=CharField())
            else:
                annotations["project"] = F("namespace")

        if is_grouped_by_node(self.parameters):
            # This adds the instance counts to the node group by.
            if self._mapper.report_type_map.get("capacity_aggregate", {}).get("node"):
                self.report_annotations.update(
                    self._mapper.report_type_map.get("capacity_aggregate", {}).get("node", {})
                )
        for tag_db_name, _, original_tag in self._tag_group_by:
            annotations[tag_db_name] = KT(f"{self._mapper.tag_column}__{original_tag}")

        if special_annotations := self._mapper.report_type_map.get("report_type_annotations"):
            annotations.update(special_annotations)

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

    def format_tags(self, tags_iterable):
        """
        Formats the tags into our standard format.
        """
        if not tags_iterable:
            return []
        transformed_tags = defaultdict(lambda: {"values": set()})

        for tag in tags_iterable:
            if tag:
                for key, value in tag.items():
                    transformed_tags[key]["values"].add(value)

        return [{"key": key, "values": list(data["values"])} for key, data in transformed_tags.items()]

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
        if "score" in self.query_sum:
            self.query_sum["total_score"] = self.query_sum.pop("score")
        output["total"] = self.query_sum

        if self._delta:
            output["delta"] = self.query_delta

        return output

    def _pack_score(self, row, should_compute):
        """Shape efficiency annotations into the score response object.

        wasted_cost comes from the provider map's pre-computed column sum and is always
        included. usage_efficiency_percent is a ratio-of-sums that is only meaningful
        when should_compute is True (single GROUP BY dimension, no tag interaction).
        """
        score: dict = {}
        if should_compute:
            score["usage_efficiency_percent"] = row.pop("usage_efficiency", 0)
        else:
            row.pop("usage_efficiency", None)

        wasted = row.pop("wasted_cost", None)
        if wasted is not None:
            score["wasted_cost"] = {"value": wasted, "units": self.currency}

        row["score"] = score

    def _rate_sum_by_source(self, metric_names: frozenset) -> dict:
        """Return {source_uuid_str: sum_of_flat_tier_values_in_cost_model_currency}.

        Parses CostModel.rates (a JSON list) and sums all rate values whose metric
        name is in metric_names.  Two structures are handled:

        * ``tiered_rates`` – a list of tier dicts each with a ``value`` key.
        * ``tag_rates``    – a dict with a ``tag_values`` list; only entries where
          ``default`` is true are included.  These apply to every pod that does not
          match a more-specific tag value (in practice, to all pods in the common
          case of a single-value tag rule with ``default: true``).
        """
        rate_by_cm: dict = {}
        for row in CostModel.objects.all().values("uuid", "rates"):
            total = Decimal("0")
            for rate_entry in row["rates"] or []:
                if rate_entry.get("metric", {}).get("name") in metric_names:
                    for tier in rate_entry.get("tiered_rates", []):
                        total += Decimal(str(tier.get("value", 0)))
                    for tv in (rate_entry.get("tag_rates", {}) or {}).get("tag_values", []) or []:
                        if tv.get("default"):
                            total += Decimal(str(tv.get("value", 0)))
            rate_by_cm[str(row["uuid"])] = total

        return {
            str(mapping_row["provider_uuid"]): rate_by_cm.get(str(mapping_row["cost_model_id"]), Decimal("0"))
            for mapping_row in CostModelMap.objects.all().values("provider_uuid", "cost_model_id")
        }

    def _line_item_wasted_cost(self, group_by: list) -> dict:
        """Compute wasted_cost from OCPUsageLineItemDailySummary at daily per-pod grain.

        OCP pod summary tables (OCPPodSummaryP, etc.) aggregate across all pods within
        a cluster/namespace/node before storing. When over-utilised and under-utilised
        pods are pooled together their usage/request ratio approaches 1, driving the
        waste formula toward zero at the bucket level while real per-pod waste remains.
        This method queries the finest available grain (per-pod daily rows) so the
        clamped-waste formula is evaluated before any cross-pod aggregation.

        The per-row cost basis is:
          max(usage, request) × total_rate_from_cost_model × exchange_rate
          + infrastructure_raw_cost × infra_exchange_rate
          + infrastructure_markup_cost × infra_exchange_rate

        max(usage, request) is evaluated on the already-aggregated row (not the stored
        pod_effective_usage field, which is sum(max(u_i, r_i)) per individual pod and
        can exceed max(sum_u, sum_r) when the group contains both over- and
        under-utilised pods). Using the row-level max matches the product's wasted-cost
        definition and the integration test fixture.

        Rates are read from the CostModel table at query time so the computation is
        correct whether or not the cost model application SQL has already run.
        Only original rows (cost_model_rate_type IS NULL) are queried to avoid
        double-counting when the cost model has been applied.

        Args:
            group_by: the query_group_by list used by execute_query (["date", ...]).

        Returns:
            A dict keyed by tuple(*group_by field values) → Decimal waste.
            The sentinel key '__total__' holds the overall waste sum.
        """
        _dec = DecimalField(max_digits=33, decimal_places=15)

        if self._report_type == "cpu":
            usage_field = "pod_usage_cpu_core_hours"
            effective_field = "pod_effective_usage_cpu_core_hours"
            rate_by_source = self._rate_sum_by_source(self._CPU_HOUR_METRICS)
        else:
            usage_field = "pod_usage_memory_gigabyte_hours"
            effective_field = "pod_effective_usage_memory_gigabyte_hours"
            rate_by_source = self._rate_sum_by_source(self._MEM_HOUR_METRICS)

        # Per-source rate annotation: Case(When(source_uuid=X, then=rate_X), ..., default=0)
        rate_whens = [
            When(**{"source_uuid": uuid, "then": Value(rate, output_field=_dec)})
            for uuid, rate in rate_by_source.items()
            if rate
        ]
        rate_ann = (
            Case(*rate_whens, default=Value(Decimal("0"), output_field=_dec), output_field=_dec)
            if rate_whens
            else Value(Decimal("0"), output_field=_dec)
        )

        row_infra = Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=_dec))
        row_markup = Coalesce(F("infrastructure_markup_cost"), Value(0, output_field=_dec))
        row_u = Coalesce(F(usage_field), Value(0, output_field=_dec))

        # pod_effective_usage_*_hours stores SUM(MAX(usage_i, request_i)) aggregated
        # across all raw intervals in the day. This preserves the per-interval clamping
        # so that hours where a pod is over-utilised contribute MAX(u_i, r_i) = u_i
        # (no waste for that interval) rather than collapsing to MAX(SUM(u), SUM(r))
        # which would incorrectly cancel within-day over/under utilisation swings.
        # waste = (effective - usage) * rate = SUM(MAX(0, r_i - u_i)) * rate  ✓
        row_eff = Coalesce(F(effective_field), Value(0, output_field=_dec))

        per_row_cost = (
            # Cloud infrastructure cost converted to the report currency
            (row_infra + row_markup) * Coalesce(F("infra_exchange_rate"), Value(1, output_field=_dec))
            # Cost model contribution: rate × effective_usage → report currency.
            # effective_usage = SUM(MAX(u_i, r_i)) already encodes the per-interval
            # clamp, giving the correct cost basis for the waste formula.
            + row_eff * F("_wc_rate") * Coalesce(F("exchange_rate"), Value(1, output_field=_dec))
        )
        # waste = per_row_cost × (1 − usage/effective) = (effective − usage) × rate
        # Uses effective in the denominator (not request) so the ratio is always in [0,1]
        # and the result equals the fixture's SUM(MAX(0, r_i − u_i)) × rate per group.
        per_row_waste = Coalesce(
            Greatest(
                per_row_cost * (Value(1, output_field=_dec) - row_u / NullIf(row_eff, Value(0, output_field=_dec))),
                Value(0, output_field=_dec),
            ),
            Value(0, output_field=_dec),
        )
        waste_ann = Coalesce(Sum(per_row_waste), Value(0, output_field=_dec), output_field=_dec)

        # Original rows only: cost model application creates additional rows in the same
        # table with cost_model_rate_type set. Querying only original rows avoids double-
        # counting and gives the correct per-pod-group grain.
        li_q = OCPUsageLineItemDailySummary.objects.filter(self.query_filter)
        li_q = li_q.filter(cost_model_rate_type__isnull=True)
        li_q = li_q.exclude(namespace__in=self._SENTINEL_NAMESPACES)
        if self.query_exclusions:
            li_q = li_q.exclude(self.query_exclusions)

        # Build a minimal annotation set to avoid GROUP BY pollution.
        # Applying self.annotations directly adds cluster, currency_annotation, etc.
        # as non-aggregate expressions which Django may include in GROUP BY,
        # fragmenting groups beyond the intended dimensions.
        fresh_ann: dict = {
            "date": self.date_trunc("usage_start"),
            "_wc_rate": rate_ann,
            **self.exchange_rate_annotation_dict,
        }
        for gb in group_by:
            if gb != "date" and gb in self.annotations:
                fresh_ann[gb] = self.annotations[gb]
        li_q = li_q.annotate(**fresh_ann)

        total = li_q.aggregate(wasted_cost=waste_ann)["wasted_cost"] or Decimal(0)
        by_group = {
            tuple(row[g] for g in group_by): row["wasted_cost"]
            for row in li_q.values(*group_by).annotate(wasted_cost=waste_ann)
        }
        by_group["__total__"] = total
        return by_group

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

            row_annotations = {k: v for k, v in self.report_annotations.items() if k not in group_by_value}
            query_data = query.values(*query_group_by).annotate(**row_annotations)

            if is_grouped_by_project(self.parameters):
                query_data = self._project_classification_annotation(query_data)
            if self._limit and query_data:
                query_data = self._group_by_ranks(query, query_data)
                order_by = self.parameters.get("order_by")
                if not order_by or set(order_by).intersection(["cost_total", "cost_total_distributed"]):
                    # https://issues.redhat.com/browse/COST-3901
                    # order_by[distributed_cost] is required for distributing platform cost,
                    # therefore others must be at the end.
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
                calculate_unused(query_sum)

            if self._report_type in ("cpu", "memory"):
                has_tag_interaction = self._tag_group_by or self.get_tag_filter_keys()
                should_compute = not has_tag_interaction and len(group_by_value) <= 1
                self._pack_score(query_sum, should_compute)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            query_data = self.order_by(query_data, query_order_by)

            if self._report_type in ("cpu", "memory"):
                for row in query_data:
                    self._pack_score(row, should_compute)

            for row in query_data:
                if tag_iterable := row.get("tags"):
                    row["tags"] = self.format_tags(tag_iterable)

            if self.is_csv_output:
                if self._report_type == "virtual_machines":
                    date_string = self.date_to_string(self.time_interval[0])
                    data = [{"date": date_string, "vm_names": query_data}]
                else:
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

    # Capacity Calculations

    def get_capacity(self, query_data):
        """Calculate capacity & instance count for all nodes over the date range."""
        q_table = self._mapper.query_table
        LOG.debug(f"Using query table: {q_table}")
        query = q_table.objects.filter(self.query_filter)
        if self.query_exclusions:
            query = query.exclude(self.query_exclusions)
        with tenant_context(self.tenant):
            _class = NodeCapacity if is_grouped_by_node(self.parameters) else ClusterCapacity
            capacity = _class(self._mapper.report_type_map, query, self.resolution)
            if not capacity.capacity_aggregate:
                # short circuit for if the capacity dataclass in report provider map
                return query_data, {}
            capacity.populate_dataclass()
        for row in query_data:
            capacity.update_row(row, self.parameters.get("start_date"))
        return query_data, capacity.generate_query_sum()

    # Delta Calculations

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
