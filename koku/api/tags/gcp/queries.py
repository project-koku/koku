#
# Copyright 2021 Red Hat, Inc.
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
"""GCP Tag Query Handling."""
import logging
from copy import deepcopy

from api.models import Provider
from api.report.gcp.provider_map import GCPProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import GCPTagsSummary
from reporting.provider.gcp.models import GCPTagsValues


LOG = logging.getLogger(__name__)


class GCPTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for GCP."""

    provider = Provider.PROVIDER_GCP
    data_sources = [{"db_table": GCPTagsSummary, "db_column_period": "cost_entry_bill__billing_period"}]
    TAGS_VALUES_SOURCE = [{"db_table": GCPTagsValues, "fields": ["key"]}]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["account", "project"]

    def __init__(self, parameters):
        """Establish GCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        if not hasattr(self, "_mapper"):
            self._mapper = GCPProviderMap(provider=self.provider, report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    @property
    def filter_map(self):
        """Establish which filter map to use based on tag API."""
        filter_map = deepcopy(TagQueryHandler.FILTER_MAP)
        if self._parameters.get_filter("value"):
            filter_map.update(
                {
                    "account": [
                        {"field": "account_ids", "operation": "icontains", "composition_key": "account_filter"}
                    ],
                    "project": [
                        {"field": "project_names", "operation": "icontains", "composition_key": "project_filter"}
                    ],
                }
            )
        else:
            filter_map.update(
                {
                    "account": [
                        {"field": "account_id", "operation": "icontains", "composition_key": "account_filter"}
                    ],
                    "project": [
                        {"field": "project_name", "operation": "icontains", "composition_key": "project_filter"}
                    ],
                }
            )
        return filter_map
