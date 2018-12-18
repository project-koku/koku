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
"""Query Handling for Tags."""
import logging

from api.query_handler import QueryHandler

LOG = logging.getLogger(__name__)


class TagQueryHandler(QueryHandler):
    """Handles tag queries and responses."""

    def __init__(self, query_parameters, url_data,
                 tenant, **kwargs):
        """Establish tag query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        default_ordering = {'tags': 'asc'}
        super().__init__(query_parameters, url_data,
                         tenant, default_ordering, **kwargs)
        self.query_filter = self._get_filter()

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = super()._get_filter(delta)

        composed_filters = filters.compose()

        LOG.debug(f'_get_filter: {composed_filters}')
        return composed_filters
