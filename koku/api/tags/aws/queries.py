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
"""AWS Tag Query Handling."""
from copy import deepcopy

from api.models import Provider
from api.report.aws.provider_map import AWSProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import AWSTagsSummary
from reporting.provider.aws.models import AWSTagsValues


class AWSTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for AWS."""

    provider = Provider.PROVIDER_AWS
    data_sources = [{"db_table": AWSTagsSummary, "db_column_period": "cost_entry_bill__billing_period"}]
    TAGS_VALUES_SOURCE = [{"db_table": AWSTagsValues, "fields": ["awstagssummary__key"]}]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["account"]
    FILTER_MAP = deepcopy(TagQueryHandler.FILTER_MAP)
    FILTER_MAP.update(
        {
            "account": [
                {
                    "field": "account_alias__account_alias",
                    "operation": "icontains",
                    "composition_key": "account_filter",
                },
                {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
            ]
        }
    )

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        if not hasattr(self, "_mapper"):
            self._mapper = AWSProviderMap(provider=self.provider, report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)
