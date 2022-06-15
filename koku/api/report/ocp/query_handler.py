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

import numpy as np
import pandas as pd
from django.db.models import F
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.report.ocp.provider_map import OCPProviderMap
from api.report.queries import check_if_valid_date_str
from api.report.queries import is_grouped_by_project
from api.report.queries import ReportQueryHandler
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from reporting.models import OCPUsageLineItemDailySummary

# TODO: remove this import after debugging

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

    # TODO: We most likely want to move this to its own relation table.
    def build_source_to_currency_map(self):
        """
        OCP sources do not have costs associated, so we need to
        grab the base currency from the cost model, and create
        a mapping of source_uuid to currency.

        returns:
            dict: {source_uuid: currency}

        Short Hand: cm
        """
        source_to_currency = {}
        cost_models = CostModel.objects.all().values("uuid", "currency").distinct()
        cm_to_currency = {}
        for row in cost_models:
            cm_to_currency[row["uuid"]] = row["currency"]

        mapping = CostModelMap.objects.all().values("provider_uuid", "cost_model_id")
        source_to_currency = {}
        for row in mapping:
            source_to_currency[row["provider_uuid"]] = cm_to_currency[row["cost_model_id"]]

        return source_to_currency

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

    def pandas_agg_for_currency(self, query_group_by, query_data, skip_columns, source_column):
        """Group_by[currency] and aggregate with pandas.

        Args:
            query_group_by (list): query group by.
            query_data (queryset): queryset of the query data.
            skip_columns (list): columns to skip.
            source_column (string): tells you which source column to gb.

        Returns
            (dictionary): A dictionary of query data"""

        if query_data:
            exchange_rates = {
                "EUR": {
                    "USD": Decimal(1.0718113612004287471535235454211942851543426513671875),
                    "CAD": Decimal(1.25),
                },
                "GBP": {
                    "USD": Decimal(1.25470514429109147869212392834015190601348876953125),
                    "CAD": Decimal(1.34),
                },
                "JPY": {
                    "USD": Decimal(0.007456565505927968857957655046675427001900970935821533203125),
                    "CAD": Decimal(1.34),
                },
                "AUD": {"USD": Decimal(0.7194244604), "CAD": Decimal(1.34)},
                "USD": {"USD": Decimal(1.0)},
            }
            source_mapping = self.build_source_to_currency_map()
            df = pd.DataFrame(query_data)
            columns = self._mapper.PACK_DEFINITIONS["cost_groups"]["keys"].keys()
            for column in columns:
                # temp currency version
                df[column] = df.apply(
                    lambda row: row[column]
                    * exchange_rates[source_mapping.get(row[source_column], "USD")][self.currency],
                    axis=1,
                )
                df["cost_units"] = self.currency
            skip_columns = ["gcp_project_alias"]
            if "count" not in df.columns:
                skip_columns.extend(["count", "count_units"])
            aggs = {
                col: ["max"] if "units" in col else ["sum"]
                for col in self.report_annotations
                if col not in skip_columns
            }

            grouped_df = df.groupby(query_group_by, dropna=False).agg(aggs, axis=1)
            columns = grouped_df.columns.droplevel(1)
            grouped_df.columns = columns
            grouped_df.reset_index(inplace=True)
            grouped_df = grouped_df.replace({np.nan: None})
            query_data = grouped_df.to_dict("records")

        return query_data

    def total_query_pandas_agg(self, query_sum_data, source_column):
        """Agg the query total using pandas and currency.
        Group_by[currency] and aggregate with pandas.

        Args:
            query_group_by (list): query group by.
            query_data (queryset): queryset of the query data.
            skip_columns (list): columns to skip.
            source_column (string): tells you which source column to gb.

        Returns
            (dictionary): A dictionary of query data"""

        exchange_rates = {
            "EUR": {
                "USD": Decimal(1.0718113612004287471535235454211942851543426513671875),
                "CAD": Decimal(1.25),
            },
            "GBP": {
                "USD": Decimal(1.25470514429109147869212392834015190601348876953125),
                "CAD": Decimal(1.34),
            },
            "JPY": {
                "USD": Decimal(0.007456565505927968857957655046675427001900970935821533203125),
                "CAD": Decimal(1.34),
            },
            "AUD": {"USD": Decimal(0.7194244604), "CAD": Decimal(1.34)},
            "USD": {"USD": Decimal(1.0)},
        }
        source_mapping = self.build_source_to_currency_map()
        df = pd.DataFrame(query_sum_data)
        columns = self._mapper.PACK_DEFINITIONS["cost_groups"]["keys"].keys()
        for column in columns:
            df[column] = df.apply(
                lambda row: row[column] * exchange_rates[source_mapping.get(row[source_column], "USD")][self.currency],
                axis=1,
            )
            df["cost_units"] = self.currency
        skip_columns = ["source_uuid", "gcp_project_alias", "clusters"]
        if "count" not in df.columns:
            skip_columns.extend(["count", "count_units"])
        aggs = {
            col: ["max"] if "units" in col else ["sum"] for col in self.report_annotations if col not in skip_columns
        }

        grouped_df = df.groupby([source_column]).agg(aggs, axis=1)
        columns = grouped_df.columns.droplevel(1)
        grouped_df.columns = columns
        grouped_df.reset_index(inplace=True)
        total_query = grouped_df.to_dict("records")
        query_sum = defaultdict(Decimal)

        for element in total_query:
            for key, value in element.items():
                if type(value) == Decimal:
                    query_sum[key] += value
                else:
                    query_sum[key] = value
        query_sum.pop(source_column)
        return query_sum

    def execute_query(self):  # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = self.initialize_totals()
        data = []

        with tenant_context(self.tenant):
            query = self.query_table.objects.filter(self.query_filter)
            query_data = query.annotate(**self.annotations)
            group_by_value = self._get_group_by()

            query_group_by = ["date"] + group_by_value
            initial_group_by = copy.deepcopy(query_group_by)
            source_column = "source_uuid" if self.query_table == OCPUsageLineItemDailySummary else "source_uuid_id"
            if self.query_table == OCPUsageLineItemDailySummary:
                self.report_annotations.pop("source_uuid")
            initial_group_by.append(source_column)
            annotations = self._mapper.report_type_map.get("annotations")
            query_order_by = ["-date"]
            query_order_by.extend(self.order)  # add implicit ordering

            query_data = query_data.values(*initial_group_by).annotate(**annotations)
            aggregates = self._mapper.report_type_map.get("aggregates")
            query_sum_data = query_data.annotate(**aggregates)
            skip_columns = ["gcp_project_alias"]
            query_data = self.pandas_agg_for_currency(query_group_by, query_data, skip_columns, source_column)

            if self._limit and query_data:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            # Populate the 'total' section of the API response
            if query.exists():
                query_sum = self.total_query_pandas_agg(query_sum_data, source_column)

            query_data, total_capacity = self.get_cluster_capacity(query_data)
            if total_capacity:
                query_sum.update(total_capacity)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)
            is_csv_output = self.parameters.accept_type and "text/csv" in self.parameters.accept_type

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
                data = list(query_data)
            else:
                # Pass in a copy of the group by without the added
                # tag column name prefix
                groups = copy.deepcopy(query_group_by)
                groups.remove("date")
                data = self._apply_group_by(list(query_data), groups)
                data = self._transform_data(query_group_by, 0, data)

        sum_init = {"cost_units": self._mapper.cost_units_key}
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
