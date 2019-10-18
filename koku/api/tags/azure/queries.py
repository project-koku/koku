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

from tenant_schemas.utils import tenant_context

from api.query_filter import QueryFilter
from api.report.azure.provider_map import AzureProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import AzureCostEntryLineItemDailySummary

LOG = logging.getLogger(__name__)


class AzureTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for Azure."""

    data_sources = [{'db_table': AzureCostEntryLineItemDailySummary,
                     'db_column': 'tags'}]

    SUPPORTED_FILTERS = ['subscription_guid']
    FILTER_MAP = {'subscription_guid': {'field': 'subscription_guid',
                                        'operation': 'icontains'}}
    provider = 'AZURE'

    def __init__(self, parameters):
        """Establish Azure report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        if not hasattr(self, '_mapper'):
            self._mapper = AzureProviderMap(provider=self.provider,
                                            report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    def _get_time_based_filters(self, delta=False):
        """Overridden from QueryHandler."""
        start_filter = QueryFilter(field='usage_start', operation='gte',
                                   parameter=self.start_datetime)
        end_filter = QueryFilter(field='usage_start', operation='lte',
                                 parameter=self.end_datetime)
        return start_filter, end_filter

    def get_tags(self):
        """Get a list of tags and values to validate filters."""
        type_filter = self.parameters.get_filter('type')

        merged_data = []
        with tenant_context(self.tenant):
            tag_keys = []
            for source in self.data_sources:
                if type_filter and type_filter != source.get('type'):
                    continue

                tag_keys = source.get('db_table').objects\
                    .filter(self.query_filter)\
                    .values(source.get('db_column'))\
                    .distinct()\
                    .all()

                for item in tag_keys:
                    tags = item.get('tags')
                    if not tags:
                        continue
                    for key, value in tags.items():
                        if not (key or value):
                            LOG.warning('Bad value in tags: %s', item)
                            LOG.info('Tag keys: %s', tag_keys)
                            continue
                        values = []
                        values.append(value)
                        dikt = {'key': key, 'values': values}
                        if dikt not in merged_data:
                            merged_data.append(dikt)
        return merged_data
