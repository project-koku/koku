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
"""AWS Tag Query Handling."""
from django.contrib.postgres.aggregates import ArrayAgg

from api.models import Provider
from api.organizations.provider_map import ProviderMap
from api.organizations.queries import OrgQueryHandler
from reporting.provider.aws.models import AWSOrganizationalUnit


class AWSOrgProviderMap(ProviderMap):
    """AWS Provider Map."""

    def __init__(self, provider, report_type):
        """Constructor."""
        self._mapping = [
            {
                "provider": Provider.PROVIDER_AWS,
                "report_type": {
                    "organizations": {
                        "annotations": {"accounts": ArrayAgg("account_id", distinct=True)},
                        "filter": [{}],
                        "default_ordering": {},
                    },
                    "tags": {},
                },
            }
        ]

        self.views = {"organizations": {"default": AWSOrganizationalUnit}}
        super().__init__(provider, report_type)


class AWSOrgQueryHandler(OrgQueryHandler):
    """Handles organizations queries and responses for AWS."""

    provider = Provider.PROVIDER_AWS
    data_sources = [
        {
            "db_table": AWSOrganizationalUnit,
            "created_db_column": "created_timestamp",
            "deleted_db_column": "deleted_timestamp",
            "annotations": {"accounts": ArrayAgg("account_id", distinct=True)},
            "query_values": ["org_unit_id", "org_unit_name", "org_unit_path"],
            "key_only_filter_column": "account_id",
            "org_id_column": "org_unit_id",
            "primary_key_column": "id",
            "parent_org_column": "parent_id",
        }
    ]
    SUPPORTED_FILTERS = ["account"]
    FILTER_MAP = {"account": {"field": "accounts", "operation": "icontains", "composition_key": "account_filter"}}

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        if not hasattr(self, "_mapper"):
            self._mapper = AWSOrgProviderMap(provider=self.provider, report_type=parameters.report_type)

        # super() needs to be called after _mapper is set
        super().__init__(parameters)
