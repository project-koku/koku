#
# Copyright 2018 Red Hat, Inc.
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
import logging

from api.models import Provider
from api.report.ocp_aws.query_handler import check_view_filter_and_group_by_criteria
from api.report.ocp_aws.query_handler import OCPInfrastructureReportQueryHandlerBase

LOG = logging.getLogger(__name__)


class OCPAllReportQueryHandler(OCPInfrastructureReportQueryHandlerBase):
    """Handles report queries and responses for OCP on All Infrastructure."""

    provider = Provider.OCP_ALL

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
            "AmazonVPC",
            "AmazonCloudFront",
            "AmazonRoute53",
            "AmazonAPIGateway",
            "Virtual Network",
            "VPN",
            "DNS",
            "Traffic Manager",
            "ExpressRoute",
            "Load Balancer",
            "Application Gateway",
        ]
        database_services = [
            "AmazonRDS",
            "AmazonDynamoDB",
            "AmazonElastiCache",
            "AmazonNeptune",
            "AmazonRedshift",
            "AmazonDocumentDB",
            "Database",
            "Cosmos DB",
            "Cache for Redis",
        ]
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

    def __init__(self, parameters):
        """Establish OCP report query handler.
        Args:
            parameters    (QueryParameters): parameter object for query
        """
        self._resolve_mapper(parameters)
        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
