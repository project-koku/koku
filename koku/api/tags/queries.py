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
from collections import defaultdict

from tenant_schemas.utils import tenant_context

from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
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

    provider = "TAGS"
    data_sources = []

    def __init__(self, parameters):
        """Establish tag query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        if parameters.get_filter("time_scope_value") == "-10":
            parameters.set_filter(time_scope_value="-1", time_scope_units="month", resolution="monthly")

        super().__init__(parameters)
        # super() needs to be called before calling _get_filter()
        self.query_filter = self._get_filter()

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

        composed_filters = filters.compose()

        LOG.debug(f"_get_filter: {composed_filters}")
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
        merged_data = defaultdict(list)
        final_data = []
        with tenant_context(self.tenant):
            tag_keys = {}
            for source in sources:
                if type_filter and type_filter != source.get("type"):
                    continue
                exclusion = self._get_exclusions("key")
                tag_keys = (
                    source.get("db_table")
                    .objects.filter(self.query_filter)
                    .exclude(exclusion)
                    .values("key", "values")
                    .distinct()
                    .all()
                )
                for dikt in tag_keys:
                    merged_data[dikt.get("key")].extend(dikt.get("values"))

                if source.get("type"):
                    self.append_to_final_data_with_type(final_data, merged_data, source)
                    # since sources with type are first, merged_data can be reset
                    merged_data = defaultdict(list)

            if not source.get("type"):
                self.append_to_final_data_without_type(final_data, merged_data)

        return final_data

    @staticmethod
    def _get_dictionary_for_key(dictionary_list, key):
        """Get dictionary matching key from list of dictionaries."""
        for di in dictionary_list:
            if key in di.get("key"):
                return di
        return None

    def append_to_final_data_with_type(self, final_data, merged_data, source):
        """Convert data to final list with a source type."""
        for k, v in merged_data.items():
            dikt = self._get_dictionary_for_key(final_data, k)
            if dikt and dikt.get("type") == source.get("type"):
                dikt["values"].extend(v)
            else:
                temp = {"key": k, "values": v, "type": source.get("type")}
            final_data.append(temp)

    def append_to_final_data_without_type(self, final_data, merged_data):
        """Convert data to final list without a source type."""
        for k, v in merged_data.items():
            temp = {"key": k, "values": v}
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
