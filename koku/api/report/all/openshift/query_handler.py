#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Query Handling for Reports."""
from api.models import Provider
from api.report.all.openshift.provider_map import OCPAllProviderMap
from api.report.aws.openshift.query_handler import OCPInfrastructureReportQueryHandlerBase
from api.report.queries import is_grouped_by_project


class OCPAllReportQueryHandler(OCPInfrastructureReportQueryHandlerBase):
    """Handles report queries and responses for OCP on All Infrastructure."""

    provider = Provider.OCP_ALL
    network_services = {
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
    }
    database_services = {
        "AmazonRDS",
        "AmazonDynamoDB",
        "AmazonElastiCache",
        "AmazonNeptune",
        "AmazonRedshift",
        "AmazonDocumentDB",
        "Database",
        "Cosmos DB",
        "Cache for Redis",
    }

    def __init__(self, parameters):
        """Establish OCP report query handler.
        Args:
            parameters    (QueryParameters): parameter object for query
        """
        # Update which field is used to calculate cost by group by param.
        if is_grouped_by_project(parameters):
            self._report_type = parameters.report_type + "_by_project"
            parameters.provider_map_kwargs["report_type"] = self._report_type
        self._mapper = OCPAllProviderMap(**parameters.provider_map_kwargs)

        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
