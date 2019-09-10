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
from api.query_filter import QueryFilter
from api.tags.queries import TagQueryHandler
from reporting.models import AzureCostEntryLineItemDailySummary


class AzureTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for Azure."""

    data_sources = [{'db_table': AzureCostEntryLineItemDailySummary,
                     'db_column': 'tags'}]

    def _get_time_based_filters(self, delta=False):
        """Overridden from QueryHandler."""
        if delta:
            date_delta = self._get_date_delta()
            start = self.start_datetime - date_delta
            end = self.end_datetime - date_delta
        else:
            start = self.start_datetime
            end = self.end_datetime

        start_filter = QueryFilter(field='usage_date_time', operation='gte',
                                   parameter=start)
        end_filter = QueryFilter(field='usage_date_time', operation='lte',
                                 parameter=end)
        return start_filter, end_filter
