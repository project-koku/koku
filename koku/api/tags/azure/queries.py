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
from api.report.azure.provider_map import AzureProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import AzureTagsSummary
from reporting.provider.azure.models import AzureTagsValues


LOG = logging.getLogger(__name__)


class AzureTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for Azure."""

    provider = Provider.PROVIDER_AZURE
    data_sources = [{"db_table": AzureTagsSummary, "db_column_period": "cost_entry_bill__billing_period"}]
    TAGS_VALUES_SOURCE = [{"db_table": AzureTagsValues, "fields": ["key"]}]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["subscription_guid"]

    def __init__(self, parameters):
        """Establish Azure report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        if not hasattr(self, "_mapper"):
            self._mapper = AzureProviderMap(provider=self.provider, report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    @property
    def filter_map(self):
        """Establish which filter map to use based on tag API."""
        filter_map = deepcopy(TagQueryHandler.FILTER_MAP)
        if self._parameters.get_filter("value"):
            filter_map.update({"subscription_guid": {"field": "subscription_guids", "operation": "icontains"}})
        else:
            filter_map.update({"subscription_guid": {"field": "subscription_guid", "operation": "icontains"}})
        return filter_map
