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
import inspect

from api.models import Provider
from api.report.all.openshift.provider_map import OCPAllComputeProviderMap
from api.report.all.openshift.provider_map import OCPAllDatabaseProviderMap
from api.report.all.openshift.provider_map import OCPAllNetworkProviderMap
from api.report.all.openshift.provider_map import OCPAllProviderMap
from api.report.all.openshift.provider_map import OCPAllStorageProviderMap
from api.report.ocp_aws.query_handler import OCPInfrastructureReportQueryHandlerBase
from api.report.queries import is_grouped_or_filtered_by_project
from reporting_common.models import SourceServiceProduct


class OCPAllReportQueryHandler(OCPInfrastructureReportQueryHandlerBase):
    """Handles report queries and responses for OCP on All Infrastructure."""

    provider = Provider.OCP_ALL

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

    def _resolve_mapper(self, parameters):
        orm_provider_map = {
            ("storage", None): OCPAllStorageProviderMap,
            ("instance_type", None): OCPAllComputeProviderMap,
            ("costs", "network"): OCPAllNetworkProviderMap,
            ("costs", "database"): OCPAllDatabaseProviderMap,
        }

        service_filter = parameters.get_filter("service")
        report_subtype = None
        if inspect.isclass(parameters.caller):
            view_class = parameters.caller.__name__
            if service_filter:
                if view_class == "OCPAllCostView":
                    res = (
                        SourceServiceProduct.objects.filter(source=self.provider)
                        .filter(product_codes__overlap=[f.strip("\"'") for f in service_filter])
                        .values("service_category")
                        .distinct()
                        .all()
                    )
                    if len(res) == 1:
                        report_subtype = res[0]["service_category"]
                else:
                    report_subtype = "_"  # Force the default
        else:
            report_subtype = "_"

        if is_grouped_or_filtered_by_project(parameters):
            map_report_type = self._report_type = parameters.report_type + "_by_project"
        else:
            map_report_type = parameters.report_type

        map_class_key = (parameters.report_type, report_subtype)
        provider_map_class = orm_provider_map.get(map_class_key, OCPAllProviderMap)

        self._mapper = provider_map_class(provider=self.provider, report_type=map_report_type)
