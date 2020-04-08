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
from collections import OrderedDict
from itertools import groupby

from api.query_handler import QueryHandler

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
