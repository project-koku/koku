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

from django.db.models import F, Q
from tenant_schemas.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.query_filter import QueryFilter, QueryFilterCollection
from api.query_handler import QueryHandler

LOG = logging.getLogger(__name__)


class TagQueryHandler(QueryHandler):
    """Handles tag queries and responses.

    Subclasses need to define a `data_sources` class attribute that defines the
    model objects and fields where the tagging information is stored.

    Definition:

        # a list of dicts
        data_sources = [{}, {}]

        # each dict has this structure
        dict = { 'db_table': Object,
                 'db_column': str,
                 'type': str
               }

        db_table = (Object) the model object containing tags
        db_column = (str) the field on the model containing tags
        type = (str) [optional] the type of tagging information, used for filtering

    Example:
        MyCoolTagHandler(TagQueryHandler):
            data_sources = [{'db_table': MyFirstTagModel,
                             'db_column': 'awesome_tags',
                             'type': 'awesome'},
                            {'db_table': MySecondTagModel,
                             'db_column': 'schwifty_tags',
                             'type': 'neato'}]

    """

    provider = 'TAGS'
    data_sources = []
    SUPPORTED_FILTERS = ['project', 'account']
    FILTER_MAP = {
        'project': {'field': 'namespace', 'operation': 'icontains'},
        'account': [{'field': 'account_alias__account_alias',
                     'operation': 'icontains',
                     'composition_key': 'account_filter'},
                    {'field': 'usage_account_id',
                     'operation': 'icontains',
                     'composition_key': 'account_filter'}]
    }

    def __init__(self, parameters):
        """Establish tag query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        super().__init__(parameters)
        # super() needs to be called before calling _get_filter()
        self.query_filter = self._get_filter()

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = copy.deepcopy(self.parameters.parameters)
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

        for filter_key in self.SUPPORTED_FILTERS:
            filter_value = self.parameters.get_filter(filter_key)
            if filter_value and not TagQueryHandler.has_wildcard(filter_value):
                filter_obj = self.FILTER_MAP.get(filter_key)
                if isinstance(filter_obj, list):
                    for _filt in filter_obj:
                        for item in filter_value:
                            q_filter = QueryFilter(parameter=item, **_filt)
                            filters.add(q_filter)
                else:
                    for item in filter_value:
                        q_filter = QueryFilter(parameter=item, **filter_obj)
                        filters.add(q_filter)

        # Update filters that specifiy and or or in the query parameter
        and_composed_filters = self._set_operator_specified_filters('and')
        or_composed_filters = self._set_operator_specified_filters('or')

        composed_filters = filters.compose()
        composed_filters = composed_filters & and_composed_filters & or_composed_filters

        LOG.debug(f'_get_filter: {composed_filters}')
        return composed_filters

    def _get_exclusions(self, column):
        """Create dictionary for filter parameters for exclude clause.

        For tags this is to filter items that have null values for the
        specified tag field.

        Args:
            column (str): The tag column being queried

        Returns:
            (Dict): query filter dictionary

        """
        exclusions = QueryFilterCollection()
        filt = {
            'field': column,
            'operation': 'isnull',
            'parameter': True
        }
        q_filter = QueryFilter(**filt)
        exclusions.add(q_filter)

        composed_exclusions = exclusions.compose()

        LOG.debug(f'_get_exclusions: {composed_exclusions}')
        return composed_exclusions

    def _set_operator_specified_filters(self, operator):
        """Set any filters using AND instead of OR."""
        filters = QueryFilterCollection()
        composed_filter = Q()
        for filter_key in self.SUPPORTED_FILTERS:
            operator_key = operator + ':' + filter_key
            filter_value = self.parameters.get_filter(operator_key)
            logical_operator = operator
            if filter_value and len(filter_value) < 2:
                logical_operator = 'or'
            if filter_value and not TagQueryHandler.has_wildcard(filter_value):
                filter_obj = self.FILTER_MAP.get(filter_key)
                if isinstance(filter_obj, list):
                    for _filt in filter_obj:
                        filt_filters = QueryFilterCollection()
                        for item in filter_value:
                            q_filter = QueryFilter(
                                parameter=item,
                                logical_operator=logical_operator,
                                **_filt
                            )
                            filt_filters.add(q_filter)
                        composed_filter = composed_filter | filt_filters.compose()
                else:
                    for item in filter_value:
                        q_filter = QueryFilter(
                            parameter=item,
                            logical_operator=logical_operator,
                            **filter_obj
                        )
                        filters.add(q_filter)
        if filters:
            composed_filter = composed_filter & filters.compose()

        return composed_filter

    def get_tag_keys(self, filters=True):
        """Get a list of tag keys to validate filters."""
        type_filter = self.parameters.get_filter('type')
        tag_keys = []
        with tenant_context(self.tenant):
            for source in self.data_sources:
                tag_keys_query = source.get('db_table').objects

                if filters is True:
                    tag_keys_query = tag_keys_query.filter(self.query_filter)

                if type_filter and type_filter != source.get('type'):
                    continue
                exclusion = self._get_exclusions(source.get('db_column'))
                tag_keys_query = tag_keys_query.annotate(
                    tag_keys=JSONBObjectKeys(F(source.get('db_column'))))\
                    .exclude(exclusion)\
                    .values('tag_keys')\
                    .distinct()\
                    .all()

                tag_keys_query = [tag.get('tag_keys') for tag in tag_keys_query]
                for tag_key in tag_keys_query:
                    tag_keys.append(tag_key)

        return list(set(tag_keys))

    @staticmethod
    def _get_dictionary_for_key(dictionary_list, key):
        """Get dictionary matching key from list of dictionaries."""
        for di in dictionary_list:
            if key in di.get('key'):
                return di
        return None

    def get_tags(self):
        """Get a list of tags and values to validate filters."""
        type_filter = self.parameters.get_filter('type')

        merged_data = []
        with tenant_context(self.tenant):
            tag_keys = []
            for source in self.data_sources:
                if type_filter and type_filter != source.get('type'):
                    continue
                exclusion = self._get_exclusions(source.get('db_column'))
                tag_keys = source.get('db_table').objects\
                    .filter(self.query_filter)\
                    .exclude(exclusion)\
                    .values(source.get('db_column'))\
                    .distinct()\
                    .all()
                tag_keys = [tag.get(source.get('db_column')) for tag in tag_keys]

                for item in tag_keys:
                    for key, value in item.items():
                        key_dict = TagQueryHandler._get_dictionary_for_key(merged_data, key)
                        if not key_dict:
                            new_dict = {}
                            new_dict['key'] = key
                            new_dict['values'] = [value]
                            if source.get('type'):
                                new_dict['type'] = source.get('type')
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
        if self.parameters.get('key_only'):
            tag_data = self.get_tag_keys()
            query_data = sorted(tag_data, reverse=self.order_direction == 'desc')
        else:
            tag_data = self.get_tags()
            query_data = sorted(tag_data, key=lambda k: k['key'], reverse=self.order_direction == 'desc')

        self.query_data = query_data

        return self._format_query_response()
