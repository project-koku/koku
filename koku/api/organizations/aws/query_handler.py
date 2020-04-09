#
# Copyright 2020 Red Hat, Inc.
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
"""AWS Query Handling for Organizations."""
import copy
import logging

from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.organizations.aws.provider_map import AWSOrgProviderMap
from api.organizations.queries import OrgQueryHandler

LOG = logging.getLogger(__name__)


class AWSOrgQueryHandler(OrgQueryHandler):
    """Handles report queries and responses for AWS."""

    provider = Provider.PROVIDER_AWS

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        # do not override mapper if its already set
        try:
            getattr(self, "_mapper")
        except AttributeError:
            self._mapper = AWSOrgProviderMap(provider=self.provider, report_type="organizations")

        self.group_by_options = self._mapper.provider_map.get("group_by_options")
        self._limit = parameters.get_filter("limit")
        self._data_value_list = ["org_unit_id", "org_unit_name", "org_unit_path"]

        super().__init__(parameters)

    @property
    def query_table(self):
        """Return the database table to query against."""
        query_table = self._mapper.query_table
        return query_table

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = self._initialize_response_output(self.parameters)
        for data in self.query_data:
            accounts = data["accounts"]
            if None in accounts:
                accounts = list(filter(None, accounts))
            data["accounts"] = accounts
        output["data"] = self.query_data
        return output

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        data = []
        with tenant_context(self.tenant):
            query_table = self.query_table
            query = query_table.objects.values().filter(self.query_filter)
            query_data = query.annotate()
            annotations = copy.deepcopy(self._mapper.report_type_map.get("annotations", {}))
            query_data = query_data.values(*self._data_value_list).annotate(**annotations)
            data = list(query_data)
        self.query_data = data
        return self._format_query_response()
