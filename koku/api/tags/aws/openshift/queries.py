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
"""OCP-on-AWS Tag Query Handling."""
from api.models import Provider
from api.report.aws.openshift.provider_map import OCPAWSProviderMap
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.ocp.queries import OCPTagQueryHandler
from api.utils import merge_dicts
from reporting.models import OCPAWSTagsSummary


class OCPAWSTagQueryHandler(AWSTagQueryHandler, OCPTagQueryHandler):
    """Handles tag queries and responses for OCP-on-AWS."""

    provider = Provider.OCP_AWS
    data_sources = [{"db_table": OCPAWSTagsSummary, "db_column_period": "cost_entry_bill__billing_period"}]
    SUPPORTED_FILTERS = AWSTagQueryHandler.SUPPORTED_FILTERS + OCPTagQueryHandler.SUPPORTED_FILTERS
    FILTER_MAP = merge_dicts(AWSTagQueryHandler.FILTER_MAP, OCPTagQueryHandler.FILTER_MAP)
    # override cluster since we are getting it from a different table and field(s)
    FILTER_MAP["cluster"] = [
        {"field": "cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
        {"field": "cluster_alias", "operation": "icontains", "composition_key": "cluster_filter"},
    ]

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPAWSProviderMap(provider=self.provider, report_type=parameters.report_type)
        if "enabled" in self.SUPPORTED_FILTERS:
            self.SUPPORTED_FILTERS.remove("enabled")
        if "enabled" in self.FILTER_MAP.keys():
            del self.FILTER_MAP["enabled"]

        # super() needs to be called after _mapper is set
        super().__init__(parameters)
