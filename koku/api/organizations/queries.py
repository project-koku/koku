#
# Copyright 2020 Red Hat, Inc.
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
"""Query Handling for Organizations."""
import copy
import logging
import random
import string
from collections import OrderedDict
from itertools import groupby

from django.db.models import Q

from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.query_handler import QueryHandler

LOG = logging.getLogger(__name__)

LOG = logging.getLogger(__name__)


def strip_tag_prefix(tag):
    """Remove the query tag prefix from a tag key."""
    return tag.replace("tag:", "").replace("and:", "").replace("or:", "")


def is_grouped_or_filtered_by_project(parameters):
    """Determine if grouped or filtered by project."""
    group_by = list(parameters.parameters.get("group_by", {}).keys())
    filters = list(parameters.parameters.get("filter", {}).keys())
    effects = group_by + filters
    return [key for key in effects if "project" in key]


class OrgQueryHandler(QueryHandler):
    """Handles report queries and responses."""

    def __init__(self, parameters):
        """Establish report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        LOG.debug(f"Query Params: {parameters}")
        super().__init__(parameters)

        self._tag_keys = parameters.tag_keys

        self._delta = parameters.delta
        self._offset = parameters.get_filter("offset", default=0)
        self.query_filter = self._get_filter()

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = QueryFilterCollection()
        if delta:
            date_delta = super()._get_date_delta()
            start = self.start_datetime - date_delta
            end = self.end_datetime - date_delta
        else:
            start = self.start_datetime
            end = self.end_datetime
        start_filter = QueryFilter(field="created_timestamp", operation="gte", parameter=start.date())
        end_filter = QueryFilter(field="created_timestamp", operation="lte", parameter=end.date())
        filters.add(start_filter)
        filters.add(end_filter)

        # set up filters for instance-type and storage queries.
        for filter_map in self._mapper._report_type_map.get("filter"):
            filters.add(**filter_map)

        # define filter parameters using API query params.
        composed_filters = self._get_search_filter(filters)

        LOG.debug(f"_get_filter: {composed_filters}")
        return composed_filters

    def _get_search_filter(self, filters):
        """Populate the query filter collection for search filters.

        Args:
            filters (QueryFilterCollection): collection of query filters
        Returns:
            (QueryFilterCollection): populated collection of query filters

        """
        # define filter parameters using API query params.
        fields = self._mapper._provider_map.get("filters")
        for q_param, filt in fields.items():
            group_by = self.parameters.get_group_by(q_param, list())
            filter_ = self.parameters.get_filter(q_param, list())
            list_ = list(set(group_by + filter_))  # uniquify the list
            if list_ and not OrgQueryHandler.has_wildcard(list_):
                if isinstance(filt, list):
                    for _filt in filt:
                        for item in list_:
                            q_filter = QueryFilter(parameter=item, **_filt)
                            filters.add(q_filter)
                else:
                    list_ = self._build_custom_filter_list(q_param, filt.get("custom"), list_)
                    for item in list_:
                        q_filter = QueryFilter(parameter=item, **filt)
                        filters.add(q_filter)

        # Update filters with tag filters
        # filters = self._set_tag_filters(filters)
        # filters = self._set_operator_specified_tag_filters(filters, "and")
        # filters = self._set_operator_specified_tag_filters(filters, "or")

        # Update filters that specifiy and or or in the query parameter
        and_composed_filters = self._set_operator_specified_filters("and")
        or_composed_filters = self._set_operator_specified_filters("or")
        multi_field_or_composed_filters = self._set_or_filters()
        composed_filters = filters.compose()
        composed_filters = composed_filters & and_composed_filters & or_composed_filters
        if multi_field_or_composed_filters:
            composed_filters = composed_filters & multi_field_or_composed_filters
        LOG.debug(f"_get_search_filter: {composed_filters}")
        return composed_filters

    def _build_custom_filter_list(self, filter_type, method, filter_list):
        """Replace filter list items from custom method."""
        if filter_type == "infrastructures" and method:
            for item in filter_list:
                custom_list = method(item, self.tenant)
                if not custom_list:
                    random_name = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    custom_list = [random_name]
                filter_list.remove(item)
                filter_list = list(set(filter_list + custom_list))
        return filter_list

    def _set_operator_specified_filters(self, operator):
        """Set any filters using AND instead of OR."""
        fields = self._mapper._provider_map.get("filters")
        filters = QueryFilterCollection()
        composed_filter = Q()

        for q_param, filt in fields.items():
            q_param = operator + ":" + q_param
            group_by = self.parameters.get_group_by(q_param, list())
            filter_ = self.parameters.get_filter(q_param, list())
            list_ = list(set(group_by + filter_))  # uniquify the list
            logical_operator = operator
            # This is a flexibilty feature allowing a user to set
            # a single and: value and still get a result instead
            # of erroring on validation
            if len(list_) < 2:
                logical_operator = "or"
            if list_ and not OrgQueryHandler.has_wildcard(list_):
                if isinstance(filt, list):
                    for _filt in filt:
                        filt_filters = QueryFilterCollection()
                        for item in list_:
                            q_filter = QueryFilter(parameter=item, logical_operator=logical_operator, **_filt)
                            filt_filters.add(q_filter)
                        # List filter are a complex mix of and/or logic
                        # Each filter in the list must be ORed together
                        # regardless of the operator on the item in the filter
                        # Ex:
                        # (OR:
                        #     (AND:
                        #         ('cluster_alias__icontains', 'ni'),
                        #         ('cluster_alias__icontains', 'se')
                        #     ),
                        #     (AND:
                        #         ('cluster_id__icontains', 'ni'),
                        #         ('cluster_id__icontains', 'se')
                        #     )
                        # )
                        composed_filter = composed_filter | filt_filters.compose()
                else:
                    list_ = self._build_custom_filter_list(q_param, filt.get("custom"), list_)
                    for item in list_:
                        q_filter = QueryFilter(parameter=item, logical_operator=logical_operator, **filt)
                        filters.add(q_filter)
        if filters:
            composed_filter = composed_filter & filters.compose()
        return composed_filter

    def _set_or_filters(self):
        """Create a composed filter collection of ORed filters.

        This is designed to handle specific cases in the provider_map
        not to accomodate user input via the API.

        """
        filters = QueryFilterCollection()
        or_filter = self._mapper._report_type_map.get("or_filter", [])
        for filt in or_filter:
            q_filter = QueryFilter(**filt)
            filters.add(q_filter)

        return filters.compose(logical_operator="or")

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Args:
            fields (dict): Fields to create annotations for

        Returns:
            (Dict): query annotations dictionary

        """
        raise NotImplementedError("Annotations must be defined by sub-classes.")

    @staticmethod
    def _group_data_by_list(group_by_list, group_index, data):
        """Group data by list.

        Args:
            group_by_list (List): list of strings to group data by
            data    (List): list of query results
        Returns:
            (Dict): dictionary of grouped query results or the original data

        """
        group_by_list_len = len(group_by_list)
        if group_index >= group_by_list_len:
            return data

        out_data = OrderedDict()
        curr_group = group_by_list[group_index]

        for key, group in groupby(data, lambda by: by.get(curr_group)):
            grouped = list(group)
            grouped = OrgQueryHandler._group_data_by_list(group_by_list, (group_index + 1), grouped)
            datapoint = out_data.get(key)
            if datapoint and isinstance(datapoint, dict):
                if isinstance(grouped, OrderedDict) and isinstance(datapoint, OrderedDict):
                    datapoint_keys = list(datapoint.keys())
                    grouped_keys = list(grouped.keys())
                    intersect_keys = list(set(datapoint_keys).intersection(grouped_keys))
                    if intersect_keys != []:
                        for inter_key in intersect_keys:
                            grouped[inter_key].update(datapoint[inter_key])
                out_data[key].update(grouped)
            elif datapoint and isinstance(datapoint, list):
                out_data[key] = grouped + datapoint
            else:
                out_data[key] = grouped
        return out_data

    def order_by(self, data, order_fields):
        """Order a list of dictionaries by dictionary keys.

        Args:
            data (list): Query data that has been converted from QuerySet to list.
            order_fields (list): The list of dictionary keys to order by.

        Returns
            (list): The sorted/ordered list

        """
        sorted_data = data
        for field in reversed(order_fields):
            reverse = False
            sorted_data = sorted(sorted_data, key=lambda entry: entry[field].lower(), reverse=reverse)
        return sorted_data

    def _initialize_response_output(self, parameters):
        """Initialize output response object."""
        output = copy.deepcopy(parameters.parameters)
        output.update(parameters.display_parameters)
        return output
