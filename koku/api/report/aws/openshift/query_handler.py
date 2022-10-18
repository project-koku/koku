#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Query Handling for Reports."""
import copy
import logging

from django.db.models import F
from django.db.models.functions import Coalesce
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.report.aws.openshift.provider_map import OCPAWSProviderMap
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.queries import check_if_valid_date_str
from api.report.queries import is_grouped_by_project

LOG = logging.getLogger(__name__)


class OCPInfrastructureReportQueryHandlerBase(AWSReportQueryHandler):
    """Base class for OCP on Infrastructure."""

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
            query_order_by = ["-date"]
            query_order_by.extend(self.order)  # add implicit ordering
            annotations = self._mapper.report_type_map.get("annotations")
            query_data = query.values(*query_group_by).annotate(**annotations)

            if "account" in query_group_by:
                query_data = query_data.annotate(
                    account_alias=Coalesce(F(self._mapper.provider_map.get("alias")), "usage_account_id")
                )
            if self._limit and query_data:
                query_data = self._group_by_ranks(query, query_data)
                if not self.parameters.get("order_by"):
                    # override implicit ordering when using ranked ordering.
                    query_order_by[-1] = "rank"

            if query.exists():
                aggregates = self._mapper.report_type_map.get("aggregates")
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            usage_units_value = self._mapper.report_type_map.get("usage_units_fallback")
            count_units_value = self._mapper.report_type_map.get("count_units_fallback")
            if query_data:
                if self._mapper.usage_units_key:
                    usage_units_value = query_data[0].get("usage_units")
                if self._mapper.report_type_map.get("annotations", {}).get("count_units"):
                    count_units_value = query_data[0].get("count_units")

            order_date = None
            for i, param in enumerate(query_order_by):
                if check_if_valid_date_str(param):
                    # Checks to see if the date is in the query_data
                    if any(d["date"] == param for d in query_data):
                        # Set order_date to a valid date
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
                # &order_by[cost]=desc&order_by[date]=2021-08-02
                query_data = self.order_by(query_data, query_order_by)

            if self.is_csv_output:
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
        return self._format_query_response()


class OCPAWSReportQueryHandler(OCPInfrastructureReportQueryHandlerBase):
    """Handles report queries and responses for OCP on AWS."""

    provider = Provider.OCP_AWS

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPAWSProviderMap(provider=self.provider, report_type=parameters.report_type)
        # Update which field is used to calculate cost by group by param.
        if is_grouped_by_project(parameters):
            self._report_type = parameters.report_type + "_by_project"
            self._mapper = OCPAWSProviderMap(provider=self.provider, report_type=self._report_type)
        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
        # super() needs to be called before _get_group_by is called
