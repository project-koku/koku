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
from api.models import Provider
from api.report import provider_pm_map
from api.report import provider_set_map
from api.report.ocp_aws.query_handler import OCPInfrastructureReportQueryHandlerBase
from api.report.queries import is_grouped_or_filtered_by_project


def get_key_from_value(value, dikt):
    for k, v in dikt.items():
        if value == v:
            return k
    return "ocp_all"


class OCPAllReportQueryHandler(OCPInfrastructureReportQueryHandlerBase):
    """Handles report queries and responses for OCP on All Infrastructure."""

    provider = Provider.OCP_ALL

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._report_type = parameters.report_type

        # Update which field is used to calculate cost by group by param.
        if is_grouped_or_filtered_by_project(parameters):
            self._report_type += "_by_project"

        access_providers = parameters.get("access_providers")
        provider = get_key_from_value(access_providers, provider_set_map)
        provider, pm = provider_pm_map.get(provider)
        self._mapper = pm(provider=provider, report_type=self._report_type)

        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
