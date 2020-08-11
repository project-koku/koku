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
"""Azure Tag Query Handling."""
import logging
from copy import deepcopy

from api.models import Provider
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.azure.provider_map import AzureProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import AzureTagsSummary
from reporting.provider.azure.models import AzureTagsValues


LOG = logging.getLogger(__name__)


class AzureTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for Azure."""

    provider = Provider.PROVIDER_AZURE
    data_sources = [
        {
            "db_table": AzureTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "db_values": AzureTagsValues,
        }
    ]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["subscription_guid"]
    FILTER_MAP = deepcopy(TagQueryHandler.FILTER_MAP)
    FILTER_MAP.update(
        {
            "subscription_guid": {"field": "subscription_guid", "operation": "icontains"},
            "value": {"field": "value", "operation": "icontains", "composition_key": "value_filter"},
        }
    )

    def __init__(self, parameters):
        """Establish Azure report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        if not hasattr(self, "_mapper"):
            self._mapper = AzureProviderMap(provider=self.provider, report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    def _get_key_filter(self):
        """Add new `exact` QueryFilter that filters on the key name."""
        filters = QueryFilterCollection()
        if self.parameters.get_filter("value"):
            filters.add(QueryFilter(field="azuretagssummary__key", operation="exact", parameter=self.key))
        else:
            filters.add(QueryFilter(field="key", operation="exact", parameter=self.key))
        return self.query_filter & filters.compose()
