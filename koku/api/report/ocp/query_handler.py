#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Query Handling for Reports."""
import copy
import datetime
import logging
from collections import defaultdict
from decimal import Decimal
from decimal import DivisionByZero
from decimal import InvalidOperation

from django.db.models import F
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.provider.provider_manager import ProviderManager
from api.report.ocp.provider_map import OCPProviderMap
from api.report.queries import check_if_valid_date_str
from api.report.queries import is_grouped_by_project
from api.report.queries import ReportQueryHandler
from koku.settings import KOKU_DEFAULT_CURRENCY
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary

LOG = logging.getLogger(__name__)


class OCPReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for OCP."""

    provider = Provider.PROVIDER_OCP

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPProviderMap(provider=self.provider, report_type=parameters.report_type)
        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

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
            "cost_distributed": {"key": "distributed", "group": "cost"},
            "cost_total": {"key": "total", "group": "cost"},
        }
        ocp_pack_definitions = copy.deepcopy(self._mapper.PACK_DEFINITIONS)
        ocp_pack_definitions["cost_groups"]["keys"] = ocp_pack_keys

        # Update which field is used to calculate cost by group by param.
        if is_grouped_by_project(parameters) and parameters.report_type == "costs":
            self._report_type = parameters.report_type + "_by_project"
            self._mapper = OCPProviderMap(provider=self.provider, report_type=self._report_type)

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)

        self._mapper.PACK_DEFINITIONS = ocp_pack_definitions

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Returns:
            (Dict): query annotations dictionary

        """
        annotations = {"date": self.date_trunc("usage_start")}
        # { query_param: database_field_name }
        fields = self._mapper.provider_map.get("annotations")
        for q_param, db_field in fields.items():
            annotations[q_param] = F(db_field)
        if (
            "project" in self.parameters.parameters.get("group_by", {})
            or "and:project" in self.parameters.parameters.get("group_by", {})
            or "or:project" in self.parameters.parameters.get("group_by", {})
        ):
            annotations["project"] = F("namespace")

        return annotations

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = self._initialize_response_output(self.parameters)
        output["data"] = self.query_data

        self.query_sum = self._pack_data_object(self.query_sum, **self._mapper.PACK_DEFINITIONS)
        output["total"] = self.query_sum

        if self._delta:
            output["delta"] = self.query_delta

        return output

    def _get_base_currency(self, source_uuid):
        """Look up the report base currency."""
        if source_uuid and source_uuid != "no-source_uuid_id":
            try:
                pm = ProviderManager(source_uuid)
                cost_models = pm.get_cost_models(self.tenant)
                if cost_models:
                    cm = cost_models[0]
                    return cm.currency
            except Exception:
                LOG.warning("no cost model found associated with source.")
            # maybe return account setting currency here
        return KOKU_DEFAULT_CURRENCY

    def return_total_query(self, total_queryset):
        """Return total query data for calculate_total."""
        # TODO: Cody - Could we simplfy this by using an odered dictionary.
        total_query = {
            "infra_total": 0,
            "infra_raw": 0,
            "infra_usage": 0,
            "infra_markup": 0,
            "infra_distributed": 0,
            "sup_raw": 0,
            "sup_usage": 0,
            "sup_markup": 0,
            "sup_distributed": 0,
            "sup_total": 0,
            "cost_total": 0,
            "cost_raw": 0,
            "cost_usage": 0,
            "cost_markup": 0,
            "cost_distributed": 0,
        }
        for query_set in total_queryset:
            base = self._get_base_currency(query_set.get("source_uuid_id", query_set.get("source_uuid")))
            exchange_rate = self._get_exchange_rate(base)
            for value in [
                "infra_total",
                "infra_raw",
                "infra_usage",
                "infra_markup",
                "infra_distributed",
                "sup_raw",
                "sup_total",
                "sup_usage",
                "sup_markup",
                "sup_distributed",
                "cost_total",
                "cost_raw",
                "cost_usage",
                "cost_markup",
                "cost_distributed",
            ]:
                orig_value = total_query[value]
                total_query[value] = orig_value + (query_set.get(value) * Decimal(exchange_rate))

            aggregates = self._mapper.report_type_map.get("aggregates")
            query_keys = aggregates.keys()
            for each in ["usage", "request", "limit", "capacity"]:
                orig_value = total_query.get(each, 0)
                new_val = query_set.get(each)
                if new_val is not None or (each in query_keys):
                    total_query[each] = orig_value + Decimal(new_val or 0)
        return total_query

    def _find_identity_key(self):
        """
        Finds the best identify key for order by
        """
        # If there is no group by then it is sorted by day
        group_by = None
        order_by = None
        groupby = self._get_group_by()
        if groupby:
            group_by = groupby[0]
        if self.order:
            order_by = self.order[0]
        return group_by, order_by

    # fmt: off
    def aggregate_currency_codes(self, currency_codes, extra_deltas):  # noqa: C901, E501
        """Aggregate and format the unconverted after currency."""
        # fmt: on
        order_numbers = {}
        meta_data = {}
        group_by, order_by = self._find_identity_key()
        meta_data["group_by_key"] = group_by
        total_results = {
            "date": None,
            "source_uuid": [],
            "clusters": [],
            "infrastructure": {
                "raw": {"value": 0, "units": self.currency},
                "markup": {"value": 0, "units": self.currency},
                "usage": {"value": 0, "units": self.currency},
                "distributed": {"value": 0, "units": self.currency},
                "total": {"value": 0, "units": self.currency},
            },
            "supplementary": {
                "raw": {"value": 0, "units": self.currency},
                "markup": {"value": 0, "units": self.currency},
                "usage": {"value": 0, "units": self.currency},
                "distributed": {"value": 0, "units": self.currency},
                "total": {"value": 0, "units": self.currency},
            },
            "cost": {
                "raw": {"value": 0, "units": self.currency},
                "markup": {"value": 0, "units": self.currency},
                "usage": {"value": 0, "units": self.currency},
                "distributed": {"value": 0, "units": self.currency},
                "total": {"value": 0, "units": self.currency},
            },
        }
        overall_previous_total = 0
        currencys = {}
        for currency_entry in currency_codes:
            unconverted_values = currency_entry.get("values")
            source_uuid_id = currency_entry.get("source_uuid_id", currency_entry.get("source_uuid"))
            currency = self._get_base_currency(source_uuid_id)
            exchange_rate = self._get_exchange_rate(currency)
            ui_dikts = {"total": total_results}
            for unconverted in unconverted_values:
                groupby_key_value = unconverted.get(group_by)
                date = unconverted.get("date")
                meta_data["date"] = date
                currencys_values = currencys.get(currency)
                ui_dikts["currencys"] = currencys_values
                initial_currency_ingest = False
                if currency not in currencys.keys():
                    new_structure = {}
                    for structure in ["infrastructure", "supplementary", "cost"]:
                        new_structure[structure] = {}
                        for each in ["raw", "markup", "usage", "distributed", "total"]:
                            converted = Decimal(unconverted.get(structure).get(each).get("value")) * Decimal(
                                exchange_rate
                            )
                            new_structure[structure][each] = {"value": converted, "units": self.currency}
                    initial_currency_ingest = True
                    ui_dikts["currencys"] = new_structure
                data_keys = unconverted.keys()
                remove_keys = ["source_uuid_id"]
                keys = list(filter(lambda w: w not in remove_keys, data_keys))
                for key in keys:
                    sum_previous_delta = True
                    for dikt_type, ui_view_dikt in ui_dikts.items():
                        if key in ["infrastructure", "supplementary", "cost"]:
                            if dikt_type == "currencys" and initial_currency_ingest:
                                # Don't update the currencys dikt if initial ingest
                                pass
                            else:
                                for each in ["raw", "markup", "usage", "distributed", "total"]:
                                    current_ui_value = ui_view_dikt.get(key).get(each).get("value")
                                    converted = Decimal(unconverted.get(key).get(each).get("value")) * Decimal(
                                        exchange_rate
                                    )
                                    ui_view_dikt[key][each]["value"] = Decimal(converted) + Decimal(current_ui_value)
                        elif key == "delta_value" and unconverted.get(key):
                            ui_view_dikt[key] = Decimal(ui_view_dikt.get(key, 0)) + Decimal(unconverted.get(key, 0))
                        elif key in ["usage", "request", "limit"]:
                            check_val = unconverted.get(key)
                            if check_val:
                                orig_value = ui_view_dikt.get(key)
                                if not orig_value:
                                    usage = {"value": 0, "units": None}
                                    ui_view_dikt[key] = copy.deepcopy(usage)
                                total_query_val = ui_view_dikt.get(key).get("value")
                                order_value = Decimal(check_val.get("value")) + Decimal(total_query_val)
                                ui_view_dikt[key]["value"] = order_value
                                ui_view_dikt[key]["units"] = check_val.get("units")
                                if key in order_by and groupby_key_value:
                                    if order_numbers.get(date):
                                        dict_to_update = order_numbers[date]
                                        dict_to_update[groupby_key_value] = order_value
                                    else:
                                        order_numbers[date] = {groupby_key_value: order_value}
                        elif key == "delta_percent":
                            current_delta = unconverted.get("delta_value", 0)
                            percentage = unconverted.get("delta_percent", None)
                            # To calculate the overall delta percentage we need the overall previous_total.
                            # percentage = (delta / previous_toal) * 100
                            if percentage:
                                percent_ratio = percentage / 100
                                previous_total = current_delta / percent_ratio
                                if sum_previous_delta:
                                    overall_previous_total += previous_total
                        else:
                            current_vals = ui_view_dikt.get(key, [])
                            new_val = unconverted.get(key, [])
                            if key in ["clusters", "source_uuid"]:
                                if not isinstance(current_vals, list):
                                    current_vals = [current_vals]
                                if not isinstance(new_val, list):
                                    new_val = [new_val]
                            if (
                                current_vals
                                and not isinstance(current_vals, str)
                                and not isinstance(current_vals, dict)
                            ):
                                new_val = current_vals + new_val
                            ui_view_dikt[key] = new_val
                        sum_previous_delta = False
                if initial_currency_ingest:
                    currencys[currency] = ui_dikts["currencys"]
        if total_results.get("delta_value") and overall_previous_total:
            if "__" not in self._delta:
                total_results["delta_percent"] = (total_results.get("delta_value") / overall_previous_total) * 100
            else:
                delta_dikt = {}
                deltas = self._delta.split("__")
                for each in deltas:
                    value = total_results.get(each, {}).get("value", 0)
                    delta_dikt[each] = value
                total_results["delta_percent"] = delta_dikt[deltas[0]] / delta_dikt[deltas[1]] * 100
        # add last delta check
        date = total_results.get("date")
        if date and extra_deltas and date in extra_deltas.keys():
            total_results["delta_value"] = total_results.get("delta_value") - extra_deltas.get(date, 0)
        meta_data["order_numbers"] = order_numbers
        return total_results, currencys, meta_data

    def execute_query(self):  # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = self.initialize_totals()
        data = []

        with tenant_context(self.tenant):
            group_by_value = self._get_group_by()
            is_csv_output = self.parameters.accept_type and "text/csv" in self.parameters.accept_type
            query_group_by = ["date"] + group_by_value
            if not is_csv_output:
                if self.query_table == OCPUsageLineItemDailySummary:
                    query_group_by.append("source_uuid")
                    self.report_annotations.pop("source_uuid")
                else:
                    query_group_by.append("source_uuid_id")
            query = self.query_table.objects.filter(self.query_filter)
            query_data = query.annotate(**self.annotations)
            query_order_by = ["-date"]
            query_order_by.extend(self.order)  # add implicit ordering
            query_data = query_data.values(*query_group_by).annotate(**self.report_annotations)
            if self._limit and query_data:
                query_data = self._group_by_ranks(query, query_data)
                # the no node issue is happening here
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            # Populate the 'total' section of the API response
            if query.exists():
                aggregates = self._mapper.report_type_map.get("aggregates")
                if not is_csv_output:
                    metric_sum = self.return_total_query(query_data)
                else:
                    metric_sum = query.aggregate(**aggregates)
                query_sum = {key: round(metric_sum.get(key, 0), 11) for key in aggregates}

            query_data, total_capacity = self.get_cluster_capacity(query_data)
            if total_capacity:
                query_sum.update(total_capacity)
            extra_deltas = {}
            if self._delta:
                query_data, extra_deltas = self.add_deltas(query_data, query_sum)

            order_date = None
            for i, param in enumerate(query_order_by):
                # enter
                if check_if_valid_date_str(param):
                    order_date = param
                    break
            # Remove the date order by as it is not actually used for ordering
            if order_date:
                # no enter
                sort_term = self._get_group_by()[0]
                query_order_by.pop(i)
                filtered_query_data = []
                for index in query_data:
                    for key, value in index.items():
                        if (key == "date") and (value == order_date):
                            filtered_query_data.append(index)
                ordered_data = self.order_by(filtered_query_data, query_order_by)
                order_of_interest = []
                for entry in ordered_data:
                    order_of_interest.append(entry.get(sort_term))
                # write a special order by function that iterates through the
                # rest of the days in query_data and puts them in the same order
                # return_query_data = []
                sorted_data = [item for x in order_of_interest for item in query_data if item.get(sort_term) == x]
                query_data = self.order_by(sorted_data, ["-date"])
            else:
                # enter
                query_data = self.order_by(query_data, query_order_by)

            if is_csv_output:
                if self._limit:
                    data = self._ranked_list(list(query_data))
                else:
                    data = list(query_data)
            else:
                # Pass in a copy of the group by without the added
                # tag column name prefix
                # enter
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

        self.query_data = data
        if not is_csv_output:
            groupby = self._get_group_by()
            self.query_data, order_mapping, order_numbers = self.format_for_ui_recursive(
                groupby,
                self.query_data,
                extra_deltas=extra_deltas)
            key_order_dict = self.find_key_order(order_numbers)
            # TODO: CODY - The ordering logic I came up with
            # does not work on multiple group bys.
            if len(groupby) == 1:
                # TODO: Cody - Figure out if this deepcopy is needed
                copy_data = copy.deepcopy(self.query_data)
                self.query_data = self.build_reordered(copy_data, key_order_dict, order_mapping, groupby[0])

        self.query_sum = ordered_total

        return self._format_query_response()

    def get_cluster_capacity(self, query_data):  # noqa: C901
        """Calculate cluster capacity for all nodes over the date range."""
        annotations = self._mapper.report_type_map.get("capacity_aggregate")
        if not annotations:
            return query_data, {}

        cap_key = list(annotations.keys())[0]
        total_capacity = Decimal(0)
        daily_total_capacity = defaultdict(Decimal)
        capacity_by_cluster = defaultdict(Decimal)
        capacity_by_month = defaultdict(Decimal)
        capacity_by_cluster_month = defaultdict(lambda: defaultdict(Decimal))
        daily_capacity_by_cluster = defaultdict(lambda: defaultdict(Decimal))

        q_table = self._mapper.query_table
        query = q_table.objects.filter(self.query_filter)
        query_group_by = ["usage_start", "cluster_id"]

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                cluster_id = entry.get("cluster_id", "")
                usage_start = entry.get("usage_start", "")
                month = entry.get("usage_start", "").month
                if isinstance(usage_start, datetime.date):
                    usage_start = usage_start.isoformat()
                cap_value = entry.get(cap_key, 0)
                if cap_value is None:
                    cap_value = 0
                capacity_by_cluster[cluster_id] += cap_value
                capacity_by_month[month] += cap_value
                capacity_by_cluster_month[month][cluster_id] += cap_value
                daily_capacity_by_cluster[usage_start][cluster_id] = cap_value
                daily_total_capacity[usage_start] += cap_value
                total_capacity += cap_value

        if self.resolution == "daily":
            for row in query_data:
                cluster_id = row.get("cluster")
                date = row.get("date")
                if cluster_id:
                    row[cap_key] = daily_capacity_by_cluster.get(date, {}).get(cluster_id, Decimal(0))
                else:
                    row[cap_key] = daily_total_capacity.get(date, Decimal(0))
        elif self.resolution == "monthly":
            if not self.parameters.get("start_date"):
                for row in query_data:
                    cluster_id = row.get("cluster")
                    if cluster_id:
                        row[cap_key] = capacity_by_cluster.get(cluster_id, Decimal(0))
                    else:
                        row[cap_key] = total_capacity
            else:
                for row in query_data:
                    cluster_id = row.get("cluster")
                    row_date = datetime.datetime.strptime(row.get("date"), "%Y-%m").month
                    if cluster_id:
                        row[cap_key] = capacity_by_cluster_month.get(row_date, {}).get(cluster_id, Decimal(0))
                    else:
                        row[cap_key] = capacity_by_month.get(row_date, Decimal(0))

        return query_data, {cap_key: total_capacity}

    def add_deltas(self, query_data, query_sum):
        """Calculate and add cost deltas to a result set.

        Args:
            query_data (list) The existing query data from execute_query
            query_sum (list) The sum returned by calculate_totals

        Returns:
            (dict) query data with new with keys "value" and "percent"

        """
        if "__" in self._delta:
            return (self.add_current_month_deltas(query_data, query_sum), {})
        else:
            return super().add_deltas(query_data, query_sum)

    def add_current_month_deltas(self, query_data, query_sum):
        """Add delta to the resultset using current month comparisons."""
        delta_field_one, delta_field_two = self._delta.split("__")

        for row in query_data:
            delta_value = Decimal(row.get(delta_field_one, 0)) - Decimal(row.get(delta_field_two, 0))  # noqa: W504

            row["delta_value"] = delta_value
            try:
                row["delta_percent"] = row.get(delta_field_one, 0) / row.get(delta_field_two, 0) * 100  # noqa: W504
            except (DivisionByZero, ZeroDivisionError, InvalidOperation):
                row["delta_percent"] = None

        total_delta = Decimal(query_sum.get(delta_field_one, 0)) - Decimal(  # noqa: W504
            query_sum.get(delta_field_two, 0)
        )
        try:
            total_delta_percent = (
                query_sum.get(delta_field_one, 0) / query_sum.get(delta_field_two, 0) * 100  # noqa: W504
            )
        except (DivisionByZero, ZeroDivisionError, InvalidOperation):
            total_delta_percent = None

        self.query_delta = {"value": total_delta, "percent": total_delta_percent}

        return query_data
