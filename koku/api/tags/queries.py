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

from django.db.models import Q
from tenant_schemas.utils import tenant_context

from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.query_handler import QueryHandler
from api.utils import DateHelper

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

    provider = "TAGS"
    data_sources = []
    SUPPORTED_FILTERS = []
    FILTER_MAP = {}

    dh = DateHelper()

    def __init__(self, parameters):
        """Establish tag query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        super().__init__(parameters)
        # _set_start_and_end_dates must be called after super and before _get_filter
        self._set_start_and_end_dates()
        # super() needs to be called before calling _get_filter()
        self.query_filter = self._get_filter()

    def _set_start_and_end_dates(self):
        """Set start and end dates.

        Start date must be the first of the month. This function checks the
        time_scope_value and sets the start date to either current month
        start or previous month start.

        """
        time_scope = int(self.parameters.get_filter("time_scope_value"))
        if time_scope not in (-10, -30):
            return
        month_start = self.dh.this_month_start
        if self.dh.n_days_ago(self.dh.today, -(time_scope + 1)) > month_start:
            self.start_datetime = month_start
        else:
            self.start_datetime = self.dh.last_month_start
        self.end_datetime = self.dh.today

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = copy.deepcopy(self.parameters.parameters)
        output["data"] = self.query_data

        return output

    def _get_time_based_filters(self, source, delta=False):
        if delta:
            date_delta = self._get_date_delta()
            start = self.start_datetime - date_delta
            end = self.end_datetime - date_delta
        else:
            start = self.start_datetime
            end = self.end_datetime

        # replace start/end with beginning/end of given month
        start = self.dh.month_start(start)
        end = self.dh.month_end(end)

        field_prefix = source.get("db_column_period")
        start_filter = QueryFilter(field=f"{field_prefix}_start", operation="gte", parameter=start)
        end_filter = QueryFilter(field=f"{field_prefix}_start", operation="lte", parameter=end)
        return start_filter, end_filter

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = QueryFilterCollection()
        for source in self.data_sources:
            start_filter, end_filter = self._get_time_based_filters(source, delta)
            filters.add(query_filter=start_filter)
            filters.add(query_filter=end_filter)

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
        and_composed_filters = self._set_operator_specified_filters("and")
        or_composed_filters = self._set_operator_specified_filters("or")

        composed_filters = filters.compose()
        composed_filters = composed_filters & and_composed_filters & or_composed_filters

        LOG.debug(f"_get_filter: {composed_filters}")
        return composed_filters

    def _set_operator_specified_filters(self, operator):
        """Set any filters using AND instead of OR."""
        filters = QueryFilterCollection()
        composed_filter = Q()
        for filter_key in self.SUPPORTED_FILTERS:
            operator_key = operator + ":" + filter_key
            filter_value = self.parameters.get_filter(operator_key)
            logical_operator = operator
            if filter_value and len(filter_value) < 2:
                logical_operator = "or"
            if filter_value and not TagQueryHandler.has_wildcard(filter_value):
                filter_obj = self.FILTER_MAP.get(filter_key)
                if isinstance(filter_obj, list):
                    for _filt in filter_obj:
                        filt_filters = QueryFilterCollection()
                        for item in filter_value:
                            q_filter = QueryFilter(parameter=item, logical_operator=logical_operator, **_filt)
                            filt_filters.add(q_filter)
                        composed_filter = composed_filter | filt_filters.compose()
                else:
                    for item in filter_value:
                        q_filter = QueryFilter(parameter=item, logical_operator=logical_operator, **filter_obj)
                        filters.add(q_filter)
        if filters:
            composed_filter = composed_filter & filters.compose()

        return composed_filter

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
        filt = {"field": column, "operation": "isnull", "parameter": True}
        q_filter = QueryFilter(**filt)
        exclusions.add(q_filter)

        composed_exclusions = exclusions.compose()

        LOG.debug(f"_get_exclusions: {composed_exclusions}")
        return composed_exclusions

    def get_tag_keys(self, filters=True):
        """Get a list of tag keys to validate filters."""
        type_filter = self.parameters.get_filter("type")
        tag_keys = set()
        with tenant_context(self.tenant):
            for source in self.data_sources:
                tag_keys_query = source.get("db_table").objects

                if filters is True:
                    tag_keys_query = tag_keys_query.filter(self.query_filter)

                if type_filter and type_filter != source.get("type"):
                    continue
                exclusion = self._get_exclusions("key")
                tag_keys_query = tag_keys_query.exclude(exclusion).values("key").distinct().all()

                tag_keys.update({tag.get("key") for tag in tag_keys_query})

        return list(tag_keys)

    def get_tags(self):
        """Get a list of tags and values to validate filters.

        Return a list of dictionaries containing the tag keys.
        If OCP, these dicationaries will return as:
            [
                {"key": key1, "values": [value1, value2], "type": "storage" (or "pod")},
                {"key": key2, "values": [value1, value2], "type": "storage" (or "pod")},
                etc.
            ]
        If cloud provider, dicitonaries will be:
            [
                {"key": key1, "values": [value1, value2]},
                {"key": key2, "values": [value1, value2]},
                etc.
            ]
        """
        type_filter = self.parameters.get_filter("type")

        # Sort the data_sources so that those with a "type" go first
        sources = sorted(self.data_sources, key=lambda dikt: dikt.get("type", ""), reverse=True)
        final_data = []
        with tenant_context(self.tenant):
            tag_keys = {}
            for source in sources:
                if type_filter and type_filter != source.get("type"):
                    continue
                exclusion = self._get_exclusions("key")

                tag_keys = list(
                    source.get("db_table")
                    .objects.filter(self.query_filter)
                    .exclude(exclusion)
                    .values_list("key", "values")
                    .all()
                )

                converted = self._convert_to_dict(tag_keys)

                if source.get("type"):
                    self.append_to_final_data_with_type(final_data, converted, source)
                else:
                    self.append_to_final_data_without_type(final_data, converted)

        # sort the values and deduplicate before returning
        self.deduplicate_and_sort(final_data)
        return final_data

    def deduplicate_and_sort(self, data):
        for dikt in data:
            dikt["values"] = sorted(set(dikt["values"]), reverse=self.order_direction == "desc")
        return data

    @staticmethod
    def _convert_to_dict(tup, dikt=None):
        if dikt is None:
            dikt = {}
        for k, v in tup:
            if dikt.get(k):
                dikt[k].extend(v)
            else:
                dikt[k] = v
        return dikt

    @staticmethod
    def _get_dictionary_for_key(dictionary_list, key):
        """Get dictionary matching key from list of dictionaries."""
        for di in dictionary_list:
            if key in di.get("key"):
                return di
        return None

    def append_to_final_data_with_type(self, final_data, converted_data, source):
        """Convert data to final list with a source type."""
        for k, v in converted_data.items():
            dikt = self._get_dictionary_for_key(final_data, k)
            if dikt and dikt.get("type") == source.get("type"):
                dikt["values"].extend(v)
            else:
                temp = {"key": k, "values": list(v), "type": source.get("type")}
                final_data.append(temp)

    def append_to_final_data_without_type(self, final_data, converted_data):
        """Convert data to final list without a source type."""
        for k, v in converted_data.items():
            dikt = self._get_dictionary_for_key(final_data, k)
            if dikt and dikt.get("type") is None:
                dikt["values"].extend(v)
            elif not dikt:
                temp = {"key": k, "values": list(v)}
                final_data.append(temp)

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params and data

        """
        if self.parameters.get("key_only"):
            tag_data = self.get_tag_keys()
            query_data = sorted(tag_data, reverse=self.order_direction == "desc")
        else:
            tag_data = self.get_tags()
            query_data = sorted(tag_data, key=lambda k: k["key"], reverse=self.order_direction == "desc")

        self.query_data = query_data

        return self._format_query_response()
