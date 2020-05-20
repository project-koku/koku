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
"""AWS Org Unit Query Handling."""
from api.models import Provider
from api.organizations.aws.provider_map import AWSOrgProviderMap
from api.organizations.queries import OrgQueryHandler
from reporting.provider.aws.models import AWSOrganizationalUnit


class AWSOrgQueryHandler(OrgQueryHandler):
    """Handles organizations queries and responses for AWS."""

    provider = Provider.PROVIDER_AWS
    data_sources = [
        {
            "db_table": AWSOrganizationalUnit,
            "created_time_column": "created_timestamp",
            "deleted_time_column": "deleted_timestamp",
            "account_alias_column": "account_alias",
            "org_id_column": "org_unit_id",
            "org_path_column": "org_unit_path",
            "org_name_column": "org_unit_name",
            "level_column": "level",
        }
    ]
    SUPPORTED_FILTERS = ["org_unit_id"]
    FILTER_MAP = {"org_unit_id": {"field": "org_unit_id", "operation": "icontains", "composition_key": "org_filter"}}

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        if not hasattr(self, "_mapper"):
            self._mapper = AWSOrgProviderMap(provider=self.provider, report_type=parameters.report_type)

        # super() needs to be called after _mapper is set
        super().__init__(parameters)
