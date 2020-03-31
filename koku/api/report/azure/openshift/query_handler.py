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
"""OCP Query Handling for Reports."""
import copy
import logging

from django.db.models import F
from django.db.models import Value
from django.db.models import Window
from django.db.models.functions import Concat
from django.db.models.functions import RowNumber
from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.report.azure.openshift.provider_map import OCPAzureProviderMap
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.ocp_aws.query_handler import check_view_filter_and_group_by_criteria
from api.report.queries import is_grouped_or_filtered_by_project

LOG = logging.getLogger(__name__)


class OCPAzureReportQueryHandler(AzureReportQueryHandler):
    """Handles report queries and responses for OCP on Azure."""

    provider = Provider.OCP_AZURE

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPAzureProviderMap(provider=self.provider, report_type=parameters.report_type)
        # Update which field is used to calculate cost by group by param.
        if is_grouped_or_filtered_by_project(parameters):
            self._report_type = parameters.report_type + "_by_project"
            self._mapper = OCPAzureProviderMap(provider=self.provider, report_type=self._report_type)

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
            annotations[q_param] = Concat(db_field, Value(""))
        if (
            "project" in self.parameters.parameters.get("group_by", {})
            or "and:project" in self.parameters.parameters.get("group_by", {})
            or "or:project" in self.parameters.parameters.get("group_by", {})
        ):
            annotations["project"] = Concat("namespace", Value(""))

        return annotations

    @property
    def query_table(self):
        """Return the database table to query against."""
        query_table = self._mapper.query_table
        report_type = self.parameters.report_type
        report_group = "default"

        excluded_filters = {"time_scope_value", "time_scope_units", "resolution", "limit", "offset"}

        filter_keys = set(self.parameters.get("filter", {}).keys())
        filter_keys = filter_keys.difference(excluded_filters)
        group_by_keys = list(self.parameters.get("group_by", {}).keys())

        if not check_view_filter_and_group_by_criteria(filter_keys, group_by_keys):
            return query_table

        # Special Casess for Network and Database Cards in the UI
        service_filter = set(self.parameters.get("filter", {}).get("service", []))
        network_services = [
            "Virtual Network",
            "VPN",
            "DNS",
            "Traffic Manager",
            "ExpressRoute",
            "Load Balancer",
            "Application Gateway",
        ]
        database_services = ["Cosmos DB", "Cache for Redis", "Database"]
        if report_type == "costs" and service_filter and not service_filter.difference(network_services):
            report_type = "network"
        elif report_type == "costs" and service_filter and not service_filter.difference(database_services):
            report_type = "database"

        if group_by_keys:
            report_group = group_by_keys[0]
        elif filter_keys and not group_by_keys:
            report_group = list(filter_keys)[0]
        try:
            query_table = self._mapper.views[report_type][report_group]
        except KeyError:
            msg = f"{report_group} for {report_type} has no entry in views. Using the default."
            LOG.warning(msg)
        return query_table

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
            query_order_by = ["-date"]
            query_order_by.extend([self.order])

            annotations = self._mapper.report_type_map.get("annotations")
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            if self._limit:
                rank_order = getattr(F(self.order_field), self.order_direction)()
                rank_by_total = Window(expression=RowNumber(), partition_by=F("date"), order_by=rank_order)
                query_data = query_data.annotate(rank=rank_by_total)
                query_order_by.insert(1, "rank")
                query_data = self._ranked_list(query_data)

            if query.exists():
                aggregates = self._mapper.report_type_map.get("aggregates")
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            is_csv_output = self.parameters.accept_type and "text/csv" in self.parameters.accept_type
            query_data = self.order_by(query_data, query_order_by)
            cost_units_value = self._mapper.report_type_map.get("cost_units_fallback", "USD")
            usage_units_value = self._mapper.report_type_map.get("usage_units_fallback")
            count_units_value = self._mapper.report_type_map.get("count_units_fallback")
            if query_data:
                cost_units_value = query_data[0].get("cost_units")
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
        query_sum["cost_units"] = cost_units_value
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
