#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Azure Query Handling for Reports."""
import copy
import logging

from django.db.models import F
from django.db.models import Value
from django.db.models import Window
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import RowNumber
from django_tenants.utils import tenant_context

from api.models import Provider
from api.report.azure.provider_map import AzureProviderMap
from api.report.queries import ReportQueryHandler

LOG = logging.getLogger(__name__)


class AzureReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for Azure."""

    provider = Provider.PROVIDER_AZURE
    network_services = {
        "Virtual Network",
        "VPN",
        "DNS",
        "Traffic Manager",
        "ExpressRoute",
        "Load Balancer",
        "Application Gateway",
    }
    database_services = {"Database", "Cosmos DB", "Cache for Redis"}

    def __init__(self, parameters):
        """Establish Azure report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        # do not override mapper if its already set
        try:
            getattr(self, "_mapper")
        except AttributeError:
            self._mapper = AzureProviderMap(provider=self.provider, report_type=parameters.report_type)

        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Returns:
            (Dict): query annotations dictionary

        """
        units_fallback = self._mapper.report_type_map.get("cost_units_fallback")
        annotations = {
            "date": self.date_trunc("usage_start"),
            "cost_units": Coalesce(self._mapper.cost_units_key, Value(units_fallback)),
        }
        if self._mapper.usage_units_key:
            units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
            annotations["usage_units"] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))

        # { query_param: database_field_name }
        fields = self._mapper.provider_map.get("annotations")
        for q_param, db_field in fields.items():
            annotations[q_param] = Concat(db_field, Value(""))
        return annotations

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = self._initialize_response_output(self.parameters)
        output["data"] = self.query_data
        output["total"] = self.query_sum

        if self._delta:
            output["delta"] = self.query_delta

        return output

    def _build_sum(self, query):
        """Build the sum results for the query."""
        sum_units = {}
        query_sum = self.initialize_totals()

        cost_units_fallback = self._mapper.report_type_map.get("cost_units_fallback")
        usage_units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
        count_units_fallback = self._mapper.report_type_map.get("count_units_fallback")

        if query.exists():
            sum_annotations = {"cost_units": Coalesce(self._mapper.cost_units_key, Value(cost_units_fallback))}
            if self._mapper.usage_units_key:
                units_fallback = self._mapper.report_type_map.get("usage_units_fallback")
                sum_annotations["usage_units"] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
            sum_query = query.annotate(**sum_annotations)

            units_value = sum_query.values("cost_units").first().get("cost_units", cost_units_fallback)
            sum_units = {"cost_units": units_value}
            if self._mapper.usage_units_key:
                units_value = sum_query.values("usage_units").first().get("usage_units", usage_units_fallback)
                sum_units["usage_units"] = units_value
            if self._mapper.report_type_map.get("annotations", {}).get("count_units"):
                sum_units["count_units"] = count_units_fallback

            query_sum = self.calculate_total(**sum_units)
        else:
            sum_units["cost_units"] = cost_units_fallback
            if self._mapper.report_type_map.get("annotations", {}).get("count_units"):
                sum_units["count_units"] = count_units_fallback
            if self._mapper.report_type_map.get("annotations", {}).get("usage_units"):
                sum_units["usage_units"] = usage_units_fallback
            query_sum.update(sum_units)
            self._pack_data_object(query_sum, **self._mapper.PACK_DEFINITIONS)
        return query_sum

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        data = []

        with tenant_context(self.tenant):
            query = self.query_table.objects.filter(self.query_filter)
            query_data = query.annotate(**self.annotations)
            query_group_by = ["date"] + self._get_group_by()
            query_order_by = ["-date"]
            query_order_by.extend([self.order])

            annotations = self._mapper.report_type_map.get("annotations")
            query_data = query_data.values(*query_group_by).annotate(**annotations)
            query_sum = self._build_sum(query)

            if self._limit:
                rank_order = getattr(F(self.order_field), self.order_direction)()
                rank_by_total = Window(expression=RowNumber(), partition_by=F("date"), order_by=rank_order)
                query_data = query_data.annotate(rank=rank_by_total)
                query_order_by.insert(1, "rank")
                query_data = self._ranked_list(query_data)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            is_csv_output = self.parameters.accept_type and "text/csv" in self.parameters.accept_type

            query_data = self.order_by(query_data, query_order_by)

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

        key_order = list(["units"] + list(annotations.keys()))
        ordered_total = {total_key: query_sum[total_key] for total_key in key_order if total_key in query_sum}
        ordered_total.update(query_sum)

        self.query_sum = ordered_total
        self.query_data = data
        return self._format_query_response()

    def calculate_total(self, **units):
        """Calculate aggregated totals for the query.

        Args:
            units (dict): The units dictionary

        Returns:
            (dict) The aggregated totals for the query

        """
        query_group_by = ["date"] + self._get_group_by()
        query = self.query_table.objects.filter(self.query_filter)
        query_data = query.annotate(**self.annotations)
        query_data = query_data.values(*query_group_by)
        aggregates = self._mapper.report_type_map.get("aggregates")
        counts = None

        total_query = query.aggregate(**aggregates)
        for unit_key, unit_value in units.items():
            total_query[unit_key] = unit_value

        if counts:
            total_query["count"] = counts
        self._pack_data_object(total_query, **self._mapper.PACK_DEFINITIONS)

        return total_query
