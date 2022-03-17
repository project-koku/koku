#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Query Handling for Reports."""
import copy
import datetime
from locale import currency
import logging
from collections import defaultdict
from decimal import Decimal
from decimal import DivisionByZero
from decimal import InvalidOperation

from django.db.models import F
from tenant_schemas.utils import tenant_context

from api.models import Provider
from cost_models.models import CostModel
from api.provider.provider_manager import ProviderManager
from koku.settings import KOKU_DEFAULT_CURRENCY
from api.report.ocp.provider_map import OCPProviderMap
from api.report.queries import is_grouped_by_project
from api.report.queries import ReportQueryHandler

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
        # super() needs to be called before _get_group_by is called

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

    def _apply_exchange_rate(self, data):
        print("\n\n\n HERE!")
        print(data)
        print("is this updating?")
        for dictionary in data:
            print("\n\n\n\ndictionary: ")
            print(dictionary)
            source_uuids = dictionary.get("source_uuid_ids")
            print("\n\n\nsource uuids: ")
            print(source_uuids)
            for each_source_uuid in source_uuids:
                new_values = []
                for key, val in each_source_uuid.items():
                    print(key)
                    print(val)
                    if key == "values":
                        for day in val:
                            print("\n\n\nThis is the most important now: ")
                            print(day)
                            if type(day) == dict:
                                day = self._apply_total_exchange(day)
                            new_values.append(day)
                        each_source_uuid[key] = new_values
        return data


    def _apply_total_exchange(self, data):
        """Overwrite this function because the structure is different for ocp."""
        print("*****LOOK HERE!!!!******")
        source_uuid = data.get("source_uuid_id")
        print(source_uuid)
        print("\n\n\Data inside total exchange")
        print(data)
        base_currency = KOKU_DEFAULT_CURRENCY
        if self._report_type == "costs":
            exchange_rate = 1
            if source_uuid:
                base_currency = self._get_base_currency(source_uuid)
                exchange_rate = self._get_exchange_rate(base_currency)
                print("this is the exchange rate: ")
                print(exchange_rate)
                print("base currency:")
                print(base_currency)
                data["currency"] = base_currency
                for key, value in data.items():
                    for key, value in data.items():
                        if key in ["infrastructure", "supplementary", "cost"]:
                            print(key)
                            for in_key, in_value in value.items():
                                print(in_key)
                                for this_key, this_value in in_value.items():
                                    print(this_key)
                                    if this_key in ["units"]:
                                        # change to currency code
                                        print("updating currency code!")
                                        in_value[this_key] = self.currency
                                    elif this_key in ["value"]:
                                        print("\n\n\n\nvalue before: ")
                                        print(this_value)
                                        print("\n\n\nvalue after: ")
                                        value_after = round(Decimal(this_value) * Decimal(exchange_rate), 9)
                                        print(value_after)
                                        in_value[this_key] = value_after
                                        # multiply and override
                                    value[in_key] = in_value
                    # if (
                    #     key.endswith("raw")
                    #     or key.endswith("usage")
                    #     or key.endswith("distributed")
                    #     or key.endswith("markup")
                    #     or key.endswith("total")
                    # ):
                    #     print("\n\n\nupdating data of ")
                    #     print(key)
                    #     data[key] = (Decimal(value) / Decimal(exchange_rate)) * Decimal(exchange_rate)
                    # elif key.endswith("units"):
                    #     print("\n\n\nupdating currency")
                    #     data[key] = self.currency
        print("\n\n\n\nDATA after inside total exchange: ")
        print(data)
        return data

    def _get_base_currency(self, source_uuid):
        """Look up the report base currency."""
        print("\n\nsource uuid: ")
        print(source_uuid)
        pm = ProviderManager(source_uuid)
        cost_models = pm.get_cost_models(self.tenant)
        if cost_models:
            cm = cost_models[0]
            return cm.currency
        return KOKU_DEFAULT_CURRENCY

    # def return_total_query(self, total_queryset):
    #     """Return total query data for calculate_total."""
    #     total_query = {
    #         "date": None,
    #         "infra_total": 0,
    #         "infra_raw": 0,
    #         "infra_usage": 0,
    #         "infra_markup": 0,
    #         "sup_raw": 0,
    #         "sup_usage": 0,
    #         "sup_markup": 0,
    #         "sup_total": 0,
    #         "cost_total": 0,
    #         "cost_raw": 0,
    #         "cost_usage": 0,
    #         "cost_markup": 0,
    #     }
    #     for query_set in total_queryset:
    #         print("\b\b\b\bqueryset: ")
    #         print(total_queryset)
    #         base = self._get_base_currency(query_set["source_uuid_id"])
    #         total_query["date"] = query_set.get("date")
    #         exchange_rate = self._get_exchange_rate(base)
    #         for value in ["infrastructure", "supplementary", "cost"]:
    #             for v in ["raw", "markup", "usage", "distributed", "total"]:
    #                 orig_value = query_set.get(value)[v]["value"]
    #                 total_query[value] = round(orig_value + Decimal(orig_value) * Decimal(exchange_rate), 9)
    #                 # print("TOTAL QUERY VALUE", total_query[value])
    #                 # print("TOTAL QUERY: ", total_query)
    #     return total_query

    def return_total_query(self, total_queryset):
        """Return total query data for calculate_total."""
        total_query = {
            "date": None,
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
            base = self._get_base_currency(query_set["source_uuid_id"])
            total_query["date"] = query_set.get("date")
            exchange_rate = self._get_exchange_rate(base)
            total_query["date"] = query_set.get("date")
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
                total_query[value] = round(orig_value + Decimal(query_set.get(value)) * Decimal(exchange_rate), 9)

        print("\n\n\n\ntotal query: ")
        print(total_query)
        return total_query

    def format_for_ui_recursive(self, groupby, out_data, org_unit_applied=False, level=-1, org_id=None, org_type=None):
        """Format the data for the UI."""
        level += 1
        overall = []
        print("\n\n\nout data: ")
        print(out_data)
        if out_data:
            if org_unit_applied:
                groupby = ["org_entitie"] + groupby
                if "account" in groupby:
                    groupby.remove("account")
            if level == len(groupby):
                new_value = []
                for value in out_data:
                    # org_applied = False
                    # if "org_entitie" in groupby:
                    #     org_applied = True
                    new_values = self.aggregate_currency_codes_ui(value)
                    new_value.append(new_values)
                return new_value
            else:
                group = groupby[level]
                if group.startswith("tags"):
                    group = group[6:]
                for value in out_data:
                    new_out_data = value.get(group + "s")
                    org_id = value.get("id")
                    org_type = value.get("type")
                    value[group + "s"] = self.format_for_ui_recursive(
                        groupby, new_out_data, level=level, org_id=org_id, org_type=org_type
                    )
                    overall.append(value)
        return overall

    def aggregate_currency_codes_ui(self, out_data):
        """Aggregate currency code info for UI."""
        all_group_by = self._get_group_by()
        codes = {
            Provider.PROVIDER_AWS: "currency_codes",
            Provider.PROVIDER_AZURE: "currencys",
            Provider.PROVIDER_GCP: "currencys",
            Provider.OCP_AZURE: "currencys",
            Provider.OCP_GCP: "currencys",
            Provider.OCP_AWS: "currency_codes",
            Provider.OCP_ALL: "currency_codes",
            Provider.PROVIDER_OCP: "source_uuid_ids"
        }
        currency_codes = out_data.get(codes.get(self.provider))
        total_query, new_codes = self.aggregate_currency_codes(currency_codes, all_group_by)
        out_data["values"] = [total_query]
        currency_list = []
        print("\n\n\nnew_codes: ")
        print(new_codes)
        for key, value in new_codes.items():
            cur_dictionary = {"currency": key, "values": [value]}
            currency_list.append(cur_dictionary)
        out_data.pop("source_uuid_ids")
        out_data["currencys"] = currency_list
        return out_data

    def get_currency_codes_ocp(self, currency_codes, all_group_by):
        """Format the same as the other endpoints."""
        currencys = {}

        for currency_entry in currency_codes:
            values = currency_entry.get("values")
            source_uuid_id = currency_entry.get("source_uuid_id")
            currency = self._get_base_currency(source_uuid_id)
            exchange_rate = self._get_exchange_rate(currency)
            for data in values:
                # currency = data.get("currency")
                if currency not in currencys.keys():
                    print("adding currency to dictionary")
                    currencys[currency] = data
                else:
                    print("currency is already in dictionary")
                    print("\n\ncurrent data")
                    print(data)
                    print("what is in currencies dictionary")
                    print(currencys.get(currency))
                    base_values = currencys.get(currency)
                    for value in ["source_uuid", "clusters"]:
                        base_val = base_values.get(value)
                        new_val = data.get(value)
                        base_values[value] = base_val + new_val
                    for delta in ["delta_value", "delta_percent"]:
                        if data.get(delta):
                            base_values[delta] = base_values.get(delta, 0) + data.get(delta)
                    for item in ["account", "account_alias", "tags_exist"]:
                        if data.get(item):
                            base_values[item] = data.get(item)
                    for group in all_group_by:
                        if group.startswith("tags"):
                            group = group[6:]
                        base_values[group] = data.get(group)
                    for structure in ["infrastructure", "supplementary", "cost"]:
                        for each in ["raw", "markup", "usage", "total", "distributed"]:
                            orig_value = base_values.get(structure).get(each).get("value")
                            # new
                            new_value = round(Decimal(data.get(structure).get(each).get("value")) * Decimal(exchange_rate), 9)
                            base_values[structure][each]["value"] = Decimal(new_value) + Decimal(orig_value)
                            # orig_value = base_values.get(structure).get(each).get("value")
                            # base_values[structure][each]["value"] = Decimal(
                            #     data.get(structure).get(each).get("value")
                            # ) + Decimal(orig_value)
        print("\n\n\n\nNEW STRUCTURE:")
        print(currencys)
        return currencys


    def aggregate_currency_codes(self, currency_codes, all_group_by):  # noqa: C901
        """Aggregate and format the data after currency."""
        new_copy = copy.deepcopy(currency_codes)
        new_codes = self.get_currency_codes_ocp(new_copy, all_group_by)
        total_query = {
            "date": None,
            "source_uuid": [],
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
        for currency_entry in currency_codes:
            values = currency_entry.get("values")
            for data in values:
                # new
                source_uuid_id = currency_entry.get("source_uuid_id")
                base_currency = self._get_base_currency(source_uuid_id)
                exchange_rate = self._get_exchange_rate(base_currency)
                # new
                source_uuids = total_query.get("source_uuid")
                total_query["date"] = data.get("date")
                total_query["source_uuid"] = source_uuids + data.get("source_uuid")
                for delta in ["delta_value", "delta_percent"]:
                    if data.get(delta):
                        total_query[delta] = total_query.get(delta, 0) + data.get(delta)
                for item in ["account", "account_alias", "tags_exist"]:
                    if data.get(item):
                        total_query[item] = data.get(item)
                for group in all_group_by:
                    if group.startswith("tags"):
                        group = group[6:]
                    total_query[group] = data.get(group)
                for structure in ["infrastructure", "supplementary", "cost"]:
                    for each in ["raw", "markup", "usage", "total", "distributed"]:
                        orig_value = total_query.get(structure).get(each).get("value")
                        # new
                        new_value = round(Decimal(data.get(structure).get(each).get("value")) * Decimal(exchange_rate), 9)
                        total_query[structure][each]["value"] = Decimal(new_value) + Decimal(orig_value)
                        # total_query[structure][each]["value"] = Decimal(
                        #     data.get(structure).get(each).get("value")
                        # ) + Decimal(orig_value)
        # new test
        return total_query, new_codes

    def execute_query(self):  # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = self.initialize_totals()
        data = []

        with tenant_context(self.tenant):
            group_by_value = self._get_group_by()
            query_group_by = ["date"] + group_by_value
            if self._report_type == "costs":
                query_group_by.append("source_uuid_id")

            query = self.query_table.objects.filter(self.query_filter)
            query_data = query.annotate(**self.annotations)
            # query_data = query_data.values(*query_group_by)
            # query_data = query_data.annotate(**self.report_annotations)
            query_order_by = ["-date"]
            query_order_by.extend(self.order)  # add implicit ordering
            # annotations = self._mapper.report_type_map.get("annotations")
            # query_data = query_data.values(*query_group_by).annotate(**annotations)
            query_data = query_data.values(*query_group_by).annotate(**self.report_annotations)

            if self._limit and query_data:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            # Populate the 'total' section of the API response
            if query.exists():
                aggregates = self._mapper.report_type_map.get("aggregates")
                if self._report_type == "costs":
                    metrics = query_data.annotate(**aggregates)
                    metric_sum = self.return_total_query(metrics)
                else:
                    metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            query_data, total_capacity = self.get_cluster_capacity(query_data)
            if total_capacity:
                query_sum.update(total_capacity)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)
            is_csv_output = self.parameters.accept_type and "text/csv" in self.parameters.accept_type

            def check_if_valid_date_str(date_str):
                """Check to see if a valid date has been passed in."""
                import ciso8601

                try:
                    ciso8601.parse_datetime(date_str)
                except ValueError:
                    return False
                except TypeError:
                    return False
                return True

            order_date = None
            for i, param in enumerate(query_order_by):
                if check_if_valid_date_str(param):
                    order_date = param
                    break
            # Remove the date order by as it is not actually used for ordering
            if order_date:
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
                query_data = self.order_by(query_data, query_order_by)

            if is_csv_output:
                if self._limit:
                    data = self._ranked_list(list(query_data))
                else:
                    data = list(query_data)
            else:
                # Pass in a copy of the group by without the added
                # tag column name prefix
                groups = copy.deepcopy(query_group_by)
                groups.remove("date")
                data = self._apply_group_by(list(query_data), groups)
                print("\n\n\ndata before: ")
                print(data)
                data = self._transform_data(query_group_by, 0, data)
                # data = self._apply_exchange_rate(data)
                print("data after:")
                print(data)

        sum_init = {"cost_units": self.currency}
        query_sum.update(sum_init)

        ordered_total = {
            total_key: query_sum[total_key] for total_key in self.report_annotations.keys() if total_key in query_sum
        }
        ordered_total.update(query_sum)

        self.query_data = data
        if self._report_type == "costs":
            groupby = self._get_group_by()
            self.query_data = self.format_for_ui_recursive(groupby, self.query_data)
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
            return self.add_current_month_deltas(query_data, query_sum)
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
