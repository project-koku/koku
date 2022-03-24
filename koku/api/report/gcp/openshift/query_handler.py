#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Query Handling for Reports."""
import copy
import logging
from decimal import Decimal

from django.db.models import F
from django.db.models import Value
from django.db.models.functions import Concat
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.report.gcp.openshift.provider_map import OCPGCPProviderMap
from api.report.gcp.query_handler import GCPReportQueryHandler
from api.report.queries import is_grouped_by_project

LOG = logging.getLogger(__name__)


class OCPGCPReportQueryHandler(GCPReportQueryHandler):
    """Handles report queries and responses for OCP on GCP."""

    provider = Provider.OCP_GCP

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPGCPProviderMap(provider=self.provider, report_type=parameters.report_type)
        # Update which field is used to calculate cost by group by param.
        if is_grouped_by_project(parameters):
            self._report_type = parameters.report_type + "_by_project"
            self._mapper = OCPGCPProviderMap(provider=self.provider, report_type=self._report_type)

        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
        # super() needs to be called before _get_group_by is called

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
        group_by_fields = self._mapper.provider_map.get("group_by_annotations")
        for group_key in self._get_group_by():
            if group_by_fields.get(group_key):
                for q_param, db_field in group_by_fields[group_key].items():
                    annotations[q_param] = Concat(db_field, Value(""))
        return annotations

    def return_total_query(self, total_queryset):
        """Return total query data for calculate_total."""
        total_query = {
            "date": None,
            "infra_total": 0,
            "infra_raw": 0,
            "infra_usage": 0,
            "infra_markup": 0,
            "infra_credit": 0,
            "sup_raw": 0,
            "sup_usage": 0,
            "sup_markup": 0,
            "sup_credit": 0,
            "sup_total": 0,
            "cost_total": 0,
            "cost_raw": 0,
            "cost_usage": 0,
            "cost_markup": 0,
            "cost_credit": 0,
        }
        for query_set in total_queryset:
            codes = {
                Provider.PROVIDER_AWS: "currency_code",
                Provider.PROVIDER_AZURE: "currency",
                Provider.PROVIDER_GCP: "currency",
                Provider.OCP_ALL: "currency_code",
                Provider.OCP_AWS: "currency_code",
                Provider.OCP_AZURE: "currency",
                Provider.OCP_GCP: "currency",
            }
            base = query_set.get(codes.get(self.provider))
            total_query["date"] = query_set.get("date")
            exchange_rate = self._get_exchange_rate(base)
            for value in [
                "infra_total",
                "infra_raw",
                "infra_usage",
                "infra_markup",
                "infra_credit",
                "sup_raw",
                "sup_total",
                "sup_usage",
                "sup_markup",
                "sup_credit",
                "cost_total",
                "cost_raw",
                "cost_usage",
                "cost_markup",
                "cost_credit",
            ]:
                orig_value = total_query[value]
                total_query[value] = round(orig_value + Decimal(query_set.get(value)) * Decimal(exchange_rate), 9)
        return total_query

    def execute_query(self):  # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = self.initialize_totals()
        data = []

        with tenant_context(self.tenant):
            is_csv_output = self.parameters.accept_type and "text/csv" in self.parameters.accept_type
            query = self.query_table.objects.filter(self.query_filter)
            query_data = query.annotate(**self.annotations)
            group_by_value = self._get_group_by()
            query_group_by = ["date"] + group_by_value
            query_order_by = ["-date"]
            if self._report_type == "costs" and not is_csv_output:
                query_group_by.append("currency")
            query_order_by.extend(self.order)  # add implicit ordering
            annotations = self._mapper.report_type_map.get("annotations")
            query_data = query_data.values(*query_group_by).annotate(**annotations)
            if self._limit and query_data:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            if query.exists():
                aggregates = self._mapper.report_type_map.get("aggregates")
                if self._report_type == "costs" and not is_csv_output:
                    metrics = query_data.annotate(**aggregates)
                    metric_sum = self.return_total_query(metrics)
                else:
                    metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

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

            usage_units_value = self._mapper.report_type_map.get("usage_units_fallback")
            count_units_value = self._mapper.report_type_map.get("count_units_fallback")
            if query_data:
                if self._mapper.usage_units_key:
                    usage_units_value = query_data[0].get("usage_units")
                if self._mapper.report_type_map.get("annotations", {}).get("count_units"):
                    count_units_value = query_data[0].get("count_units")

            if is_csv_output:
                if self._limit:
                    data = self._ranked_list(list(query_data))
                else:
                    data = list(query_data)
            else:
                groups = copy.deepcopy(query_group_by)
                groups.remove("date")
                data = self._apply_group_by(list(query_data), groups)
                data = self._transform_data(query_group_by, 0, data)

        init_order_keys = []
        query_sum["cost_units"] = self.currency
        if self._mapper.usage_units_key and usage_units_value:
            init_order_keys = ["usage_units"]
            query_sum["usage_units"] = usage_units_value
        if self._mapper.report_type_map.get("annotations", {}).get("count_units") and count_units_value:
            query_sum["count_units"] = count_units_value
        key_order = list(init_order_keys + list(annotations.keys()))
        ordered_total = {total_key: query_sum[total_key] for total_key in key_order if total_key in query_sum}
        ordered_total.update(query_sum)
        self._pack_data_object(ordered_total, **self._mapper.PACK_DEFINITIONS)

        self.query_sum = ordered_total
        self.query_data = data
        groupby = self._get_group_by()
        if self._report_type == "costs" and not is_csv_output:
            self.query_data = self.format_for_ui_recursive(groupby, self.query_data)
        return self._format_query_response()
