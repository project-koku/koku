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
import copy
import logging

from django.db.models import Count
from tenant_schemas.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.query_filter import QueryFilter
from api.query_handler import QueryHandler

LOG = logging.getLogger(__name__)


class TagQueryHandler(QueryHandler):
    """Handles tag queries and responses."""

    def __init__(self, query_parameters, url_data,
                 tenant, db_table, db_column, **kwargs):
        """Establish tag query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
            db_table  (String): Database table name containing tags
            db_column (String): Database column name containing tags
        """
        default_ordering = {'tags': 'asc'}
        super().__init__(query_parameters, url_data,
                         tenant, default_ordering, **kwargs)
        self.query_filter = self._get_filter()
        self.db_table = db_table
        self.db_column = db_column

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = copy.deepcopy(self.query_parameters)
        output['data'] = self.query_data

        return output

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = super()._get_filter(delta)

        project = self.get_query_param_data('filter', 'project')

        if project and not TagQueryHandler.has_wildcard(project):
            proj_filter = {'field': 'namespace', 'operation': 'icontains'}
            q_filter = QueryFilter(parameter=project[0], **proj_filter)
            filters.add(q_filter)

        composed_filters = filters.compose()

        LOG.debug(f'_get_filter: {composed_filters}')
        return composed_filters

    def get_tag_keys(self, filters=True):
        """Get a list of tag keys to validate filters."""
        with tenant_context(self.tenant):
            tag_keys = self.db_table.objects
            if filters is True:
                tag_keys = tag_keys.filter(self.query_filter)

            tag_keys = tag_keys.annotate(tag_keys=JSONBObjectKeys(self.db_column))\
                .values('tag_keys')\
                .annotate(tag_count=Count('tag_keys'))\
                .all()
            tag_keys = [tag.get('tag_keys') for tag in tag_keys]

        return tag_keys

    def get_tags(self):
        """Get a list of tags and values to validate filters."""
        def get_dictionary_for_key(merged_data, key):
            for di in merged_data:
                if key in di.get('key'):
                    return di
            return None

        with tenant_context(self.tenant):
            tag_keys = self.db_table.objects\
                .filter(self.query_filter)\
                .values(self.db_column)\
                .all()
            tag_keys = [tag.get(self.db_column) for tag in tag_keys]

            merged_data = []
            for item in tag_keys:
                for key, value in item.items():
                    key_dict = get_dictionary_for_key(merged_data, key)
                    if not key_dict:
                        new_dict = {}
                        new_dict['key'] = key
                        new_dict['values'] = [value]
                        merged_data.append(new_dict)
                    else:
                        if value not in key_dict.get('values'):
                            key_dict['values'].append(value)
                            key_dict['values'].sort()
        return merged_data

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params and data

        """
        if self.query_parameters.get('key_only'):
            tag_keys = self.get_tag_keys()
            query_data = sorted(tag_keys, reverse=self.order_direction == 'desc')
        else:
            tags = self.get_tags()
            query_data = sorted(tags, key=lambda k: k['key'], reverse=self.order_direction == 'desc')

        self.query_data = query_data
        return self._format_query_response()
