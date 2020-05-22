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
"""Query Handling for Reports."""
import copy
import logging
import random
import string
from collections import defaultdict
from collections import OrderedDict
from decimal import Decimal
from decimal import DivisionByZero
from decimal import InvalidOperation
from itertools import groupby
from urllib.parse import quote_plus

from django.db.models import Q
from django.db.models.expressions import OrderBy
from django.db.models.expressions import RawSQL

from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
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


class ReportQueryHandler(QueryHandler):
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
        self.query_delta = {"value": None, "percent": None}

        self.query_filter = self._get_filter()

    def initialize_totals(self):
        """Initialize the total response column values."""
        query_sum = {}
        for value in self._mapper.report_type_map.get("aggregates").keys():
            query_sum[value] = 0
        return query_sum

    def get_tag_filter_keys(self):
        """Get tag keys from filter arguments."""
        tag_filters = []
        filters = self.parameters.get("filter", {})
        for filt in filters:
            if filt in self._tag_keys:
                tag_filters.append(filt)
        return tag_filters

    def get_tag_group_by_keys(self):
        """Get tag keys from group by arguments."""
        tag_groups = []
        filters = self.parameters.get("group_by", {})
        for filt in filters:
            if filt in self._tag_keys:
                tag_groups.append(filt)
        return tag_groups

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
            if list_ and not ReportQueryHandler.has_wildcard(list_):
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
        filters = self._set_tag_filters(filters)
        filters = self._set_operator_specified_tag_filters(filters, "and")
        filters = self._set_operator_specified_tag_filters(filters, "or")

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

    def _set_tag_filters(self, filters):
        """Create tag_filters."""
        tag_column = self._mapper.tag_column
        tag_filters = self.get_tag_filter_keys()
        tag_group_by = self.get_tag_group_by_keys()
        tag_filters.extend(tag_group_by)
        tag_filters = [tag for tag in tag_filters if "and:" not in tag and "or:" not in tag]
        for tag in tag_filters:
            # Update the filter to use the label column name
            tag_db_name = tag_column + "__" + strip_tag_prefix(tag)
            filt = {"field": tag_db_name, "operation": "icontains"}
            group_by = self.parameters.get_group_by(tag, list())
            filter_ = self.parameters.get_filter(tag, list())
            list_ = list(set(group_by + filter_))  # uniquify the list
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                for item in list_:
                    q_filter = QueryFilter(parameter=item, **filt)
                    filters.add(q_filter)
        return filters

    def _set_operator_specified_tag_filters(self, filters, operator):
        """Create tag_filters."""
        tag_column = self._mapper.tag_column
        tag_filters = self.get_tag_filter_keys()
        tag_group_by = self.get_tag_group_by_keys()
        tag_filters.extend(tag_group_by)
        tag_filters = [tag for tag in tag_filters if operator + ":" in tag]
        for tag in tag_filters:
            # Update the filter to use the label column name
            tag_db_name = tag_column + "__" + strip_tag_prefix(tag)
            filt = {"field": tag_db_name, "operation": "icontains"}
            group_by = self.parameters.get_group_by(tag, list())
            filter_ = self.parameters.get_filter(tag, list())
            list_ = list(set(group_by + filter_))  # uniquify the list
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                for item in list_:
                    q_filter = QueryFilter(parameter=item, logical_operator=operator, **filt)
                    filters.add(q_filter)
        return filters

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
            if list_ and not ReportQueryHandler.has_wildcard(list_):
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

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = super()._get_filter(delta)

        # set up filters for instance-type and storage queries.
        for filter_map in self._mapper._report_type_map.get("filter"):
            filters.add(**filter_map)

        # define filter parameters using API query params.
        composed_filters = self._get_search_filter(filters)

        LOG.debug(f"_get_filter: {composed_filters}")
        return composed_filters

    def _get_group_by(self):
        """Create list for group_by parameters."""
        group_by = []
        for item in self.group_by_options:
            group_data = self.parameters.get_group_by(item)
            if not group_data:
                group_data = self.parameters.get_group_by("and:" + item)
            if not group_data:
                group_data = self.parameters.get_group_by("or:" + item)
            if group_data:
                try:
                    group_pos = self.parameters.url_data.index(item)
                except ValueError:
                    # if we are grouping by org unit we are inserting a group by account
                    # and popping off the org_unit_id group by - but here we need to get the position
                    # for org_unit_id
                    if item == "account" and "org_unit_id" in self.parameters.url_data:
                        group_pos = self.parameters.url_data.index("org_unit_id")
                if (item, group_pos) not in group_by:
                    group_by.append((item, group_pos))

        tag_group_by = self._get_tag_group_by()
        group_by.extend(tag_group_by)
        group_by = sorted(group_by, key=lambda g_item: g_item[1])
        group_by = [item[0] for item in group_by]

        # This is a current workaround for AWS instance-types reports
        # It is implied that limiting is performed by account/region and
        # not by instance type when those group by params are used.
        # For that ranking to work we can't also group by instance_type.
        inherent_group_by = self._mapper._report_type_map.get("group_by")
        if inherent_group_by and not (group_by and self._limit):
            group_by = group_by + list(set(inherent_group_by) - set(group_by))

        return group_by

    def _get_tag_group_by(self):
        """Create list of tag based group by parameters."""
        group_by = []
        tag_column = self._mapper.tag_column
        tag_groups = self.get_tag_group_by_keys()
        for tag in tag_groups:
            tag_db_name = tag_column + "__" + strip_tag_prefix(tag)
            group_data = self.parameters.get_group_by(tag)
            if group_data:
                tag = quote_plus(tag)
                group_pos = self.parameters.url_data.index(tag)
                group_by.append((tag_db_name, group_pos))
        return group_by

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
            grouped = ReportQueryHandler._group_data_by_list(group_by_list, (group_index + 1), grouped)
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

    def _apply_group_null_label(self, data, groupby=None):
        """Apply any no-{group} labels needed before grouping data.

        Args:
            data (Dict): A row of the queried data
            group_by (list): An optional list of groups
        Returns:
            (Dict): Data updated with no-group labels

        """
        tag_prefix = self._mapper.tag_column + "__"
        if groupby is None:
            return data

        for group in groupby:
            if group in data and data.get(group) is None:
                value = group
                if group.startswith(tag_prefix):
                    value = group[len(tag_prefix) :]  # noqa
                group_label = f"no-{value}"
                data[group] = group_label

        return data

    def _apply_group_by(self, query_data, group_by=None):
        """Group data by date for given time interval then group by list.

        Args:
            query_data  (List(Dict)): Queried data
            group_by (list): An optional list of groups
        Returns:
            (Dict): Dictionary of grouped dictionaries

        """
        bucket_by_date = OrderedDict()

        if group_by is None:
            group_by = self._get_group_by()

        for item in self.time_interval:
            date_string = self.date_to_string(item)
            bucket_by_date[date_string] = []

        for result in query_data:
            if self._limit and result.get("rank"):
                del result["rank"]
            self._apply_group_null_label(result, group_by)
            date_string = result.get("date")
            date_bucket = bucket_by_date.get(date_string)
            if date_bucket is not None:
                date_bucket.append(result)

        for date, data_list in bucket_by_date.items():
            grouped = ReportQueryHandler._group_data_by_list(group_by, 0, data_list)
            bucket_by_date[date] = grouped
        return bucket_by_date

    def _initialize_response_output(self, parameters):
        """Initialize output response object."""
        output = copy.deepcopy(parameters.parameters)
        output.update(parameters.display_parameters)

        return output

    def _pack_data_object(self, data, **kwargs):  # noqa: C901
        """Pack data into object format."""
        tag_prefix = self._mapper.tag_column + "__"
        if not isinstance(data, dict):
            return data

        all_pack_keys = ["date", "delta_value", "delta_percent"]
        kwargs_values = kwargs.values()
        for pack_def in kwargs_values:
            remove_keys = []
            key_items = pack_def.get("keys")
            key_units = pack_def.get("units")
            if isinstance(key_items, dict):
                for data_key, group_info in key_items.items():
                    value = data.get(data_key)
                    units = data.get(key_units)
                    if value is not None and units is not None:
                        group_key = group_info.get("group")
                        new_key = group_info.get("key")
                        if data.get(group_key):
                            if isinstance(data[group_key], str):
                                # This if is to overwrite the "cost": "no-cost"
                                # that is provided by the order_by function.
                                data[group_key] = {}
                            data[group_key][new_key] = {"value": value, "units": units}
                        else:
                            data[group_key] = {}
                            data[group_key][new_key] = {"value": value, "units": units}
                        remove_keys.append(data_key)
            else:
                if key_items:
                    all_pack_keys += key_items
                for key in key_items:
                    units = data.get(key_units)
                    value = data.get(key)
                    if value is not None and units is not None:
                        data[key] = {"value": value, "units": units}
            if units is not None:
                del data[key_units]
            for key in remove_keys:
                del data[key]
        delete_keys = []
        new_data = {}
        for data_key in data.keys():
            if data_key.startswith(tag_prefix):
                new_tag = data_key[len(tag_prefix) :]  # noqa
                if new_tag in all_pack_keys:
                    new_data["tag:" + new_tag] = data[data_key]
                else:
                    new_data[new_tag] = data[data_key]
                delete_keys.append(data_key)
        for del_key in delete_keys:
            if data.get(del_key):
                del data[del_key]
        data.update(new_data)
        return data

    def _transform_data(self, groups, group_index, data):
        """Transform dictionary data points to lists."""
        tag_prefix = self._mapper.tag_column + "__"
        groups_len = len(groups)
        if not groups or group_index >= groups_len:
            pack = self._mapper.PACK_DEFINITIONS
            for item in data:
                self._pack_data_object(item, **pack)
            return data

        out_data = []
        label = "values"
        group_type = groups[group_index]
        next_group_index = group_index + 1

        if next_group_index < groups_len:
            label = groups[next_group_index] + "s"
            if label.startswith(tag_prefix):
                label = label[len(tag_prefix) :]  # noqa

        for group, group_value in data.items():
            group_title = group_type
            if group_type.startswith(tag_prefix):
                group_title = group_type[len(tag_prefix) :]  # noqa
            group_label = group
            if group is None:
                group_label = f"no-{group_title}"
            cur = {group_title: group_label, label: self._transform_data(groups, next_group_index, group_value)}
            out_data.append(cur)

        return out_data

    def order_by(self, data, order_fields):
        """Order a list of dictionaries by dictionary keys.

        Args:
            data (list): Query data that has been converted from QuerySet to list.
            order_fields (list): The list of dictionary keys to order by.

        Returns
            (list): The sorted/ordered list

        """
        numeric_ordering = [
            "date",
            "rank",
            "delta",
            "delta_percent",
            "total",
            "usage",
            "request",
            "limit",
            "sup_total",
            "infra_total",
            "cost_total",
        ]
        tag_str = "tag:"
        db_tag_prefix = self._mapper.tag_column + "__"
        sorted_data = data
        for field in reversed(order_fields):
            reverse = False
            field = field.replace("delta", "delta_percent")
            if field.startswith("-"):
                reverse = True
                field = field[1:]
            if field in numeric_ordering:
                sorted_data = sorted(
                    sorted_data, key=lambda entry: (entry[field] is None, entry[field]), reverse=reverse
                )
            elif tag_str in field:
                tag_index = field.index(tag_str) + len(tag_str)
                tag = db_tag_prefix + field[tag_index:]
                sorted_data = sorted(sorted_data, key=lambda entry: (entry[tag] is None, entry[tag]), reverse=reverse)
            else:
                for line_data in sorted_data:
                    if not line_data.get(field):
                        line_data[field] = f"no-{field}"
                sorted_data = sorted(sorted_data, key=lambda entry: entry[field].lower(), reverse=reverse)
        return sorted_data

    def get_tag_order_by(self, tag):
        """Generate an OrderBy clause forcing JSON column->key to be used.

        This is only for helping to create a Window() for purposes of grouping
        by tag.

        Args:
            tag (str): The Django formatted tag string
                       Ex. pod_labels__key

        Returns:
            OrderBy: A Django OrderBy clause using raw SQL

        """
        descending = True if self.order_direction == "desc" else False
        tag_column, tag_value = tag.split("__")
        return OrderBy(RawSQL(f"{tag_column} -> %s", (tag_value,)), descending=descending)

    def _percent_delta(self, a, b):
        """Calculate a percent delta.

        Args:
            a (int or float or Decimal) the current value
            b (int or float or Decimal) the previous value

        Returns:
            (Decimal) (a - b) / b * 100

            Returns Decimal(0) if b is zero.

        """
        try:
            return Decimal((a - b) / b * 100)
        except (DivisionByZero, ZeroDivisionError, InvalidOperation):
            return None

    def _ranked_list(self, data_list):
        """Get list of ranked items less than top.

        Args:
            data_list (List(Dict)): List of ranked data points from the same bucket
        Returns:
            List(Dict): List of data points meeting the rank criteria

        """
        rank_limited_data = OrderedDict()
        date_grouped_data = self.date_group_data(data_list)
        if data_list:
            self.max_rank = max(entry.get("rank") for entry in data_list)
        is_offset = "offset" in self.parameters.get("filter", {})

        for date in date_grouped_data:
            ranked_list = self._perform_rank_summation(date_grouped_data[date], is_offset)
            rank_limited_data[date] = ranked_list

        return self.unpack_date_grouped_data(rank_limited_data)

    # needs refactoring, but disabling pylint's complexity check for now.
    def _perform_rank_summation(self, entry, is_offset):  # noqa: C901
        """Do the actual rank limiting for rank_list."""
        other = None
        ranked_list = []
        others_list = []
        other_sums = {column: 0 for column in self._mapper.sum_columns}
        for data in entry:
            if other is None:
                other = copy.deepcopy(data)
            rank = data.get("rank")
            if rank > self._offset and rank <= self._limit + self._offset:
                ranked_list.append(data)
            else:
                others_list.append(data)
                for column in self._mapper.sum_columns:
                    other_sums[column] += data.get(column) if data.get(column) else 0

        if other is not None and others_list and not is_offset:
            num_others = len(others_list)
            others_label = f"{num_others} Others"

            if num_others == 1:
                others_label = f"{num_others} Other"

            other.update(other_sums)
            other["rank"] = self._limit + 1
            group_by = self._get_group_by()

            for group in group_by:
                other[group] = others_label

            if "account" in group_by:
                other["account_alias"] = others_label

            if "cluster" in group_by:
                other["cluster_alias"] = others_label
                exclusions = []
            else:
                # delete these labels from the Others category if we're not
                # grouping by cluster.
                exclusions = ["cluster", "cluster_alias"]

            for exclude in exclusions:
                if exclude in other:
                    del other[exclude]

            ranked_list.append(other)

        return ranked_list

    def date_group_data(self, data_list):
        """Group data by date."""
        date_grouped_data = defaultdict(list)

        for data in data_list:
            key = data.get("date")
            date_grouped_data[key].append(data)
        return date_grouped_data

    def unpack_date_grouped_data(self, date_grouped_data):
        """Return date grouped data to a flatter form."""
        return_data = []
        for date, values in date_grouped_data.items():
            for value in values:
                return_data.append(value)
        return return_data

    def _create_previous_totals(self, previous_query, query_group_by):
        """Get totals from the time period previous to the current report.

        Args:
            previous_query (Query): A Django ORM query
            query_group_by (dict): The group by dict for the current report
        Returns:
            (dict) A dictionary keyed off the grouped values for the report

        """
        date_delta = self._get_date_delta()
        # Added deltas for each grouping
        # e.g. date, account, region, availability zone, et cetera
        previous_sums = previous_query.annotate(**self.annotations)
        delta_field = self._mapper._report_type_map.get("delta_key").get(self._delta)
        delta_annotation = {self._delta: delta_field}
        previous_sums = previous_sums.values(*query_group_by).annotate(**delta_annotation)
        previous_dict = OrderedDict()
        for row in previous_sums:
            date = self.string_to_date(row["date"])
            date = date + date_delta
            row["date"] = self.date_to_string(date)
            key = tuple(row[key] for key in query_group_by)
            previous_dict[key] = row[self._delta]

        return previous_dict

    def _get_previous_totals_filter(self, filter_dates):
        """Filter previous time range to exlude days from the current range.

        Specifically this covers days in the current range that have not yet
        happened, but that data exists for in the previous range.

        Args:
            filter_dates (list) A list of date strings of dates to filter

        Returns:
            (django.db.models.query_utils.Q) The OR date filter

        """
        date_delta = self._get_date_delta()
        prev_total_filters = None

        for i in range(len(filter_dates)):
            date = self.string_to_date(filter_dates[i])
            date = date - date_delta
            filter_dates[i] = self.date_to_string(date)

        for date in filter_dates:
            if prev_total_filters:
                prev_total_filters = prev_total_filters | Q(usage_start=date)
            else:
                prev_total_filters = Q(usage_start=date)
        return prev_total_filters

    def add_deltas(self, query_data, query_sum):
        """Calculate and add cost deltas to a result set.

        Args:
            query_data (list) The existing query data from execute_query
            query_sum (list) The sum returned by calculate_totals

        Returns:
            (dict) query data with new with keys "value" and "percent"

        """
        delta_group_by = ["date"] + self._get_group_by()
        delta_filter = self._get_filter(delta=True)
        previous_query = self.query_table.objects.filter(delta_filter)
        previous_dict = self._create_previous_totals(previous_query, delta_group_by)
        for row in query_data:
            key = tuple(row[key] for key in delta_group_by)
            previous_total = previous_dict.get(key) or 0
            current_total = row.get(self._delta) or 0
            row["delta_value"] = current_total - previous_total
            row["delta_percent"] = self._percent_delta(current_total, previous_total)
        # Calculate the delta on the total aggregate
        if self._delta in query_sum:
            if isinstance(query_sum.get(self._delta), dict):
                current_total_sum = Decimal(query_sum.get(self._delta, {}).get("value") or 0)
            else:
                current_total_sum = Decimal(query_sum.get(self._delta) or 0)
        else:
            if isinstance(query_sum.get("cost"), dict):
                current_total_sum = Decimal(query_sum.get("cost", {}).get("total").get("value") or 0)
            else:
                current_total_sum = Decimal(query_sum.get("cost") or 0)
        delta_field = self._mapper._report_type_map.get("delta_key").get(self._delta)
        prev_total_sum = previous_query.aggregate(value=delta_field)
        if self.resolution == "daily":
            dates = [entry.get("date") for entry in query_data]
            prev_total_filters = self._get_previous_totals_filter(dates)
            if prev_total_filters:
                prev_total_sum = previous_query.filter(prev_total_filters).aggregate(value=delta_field)

        prev_total_sum = Decimal(prev_total_sum.get("value") or 0)

        total_delta = current_total_sum - prev_total_sum
        total_delta_percent = self._percent_delta(current_total_sum, prev_total_sum)

        self.query_delta = {"value": total_delta, "percent": total_delta_percent}

        if self.order_field == "delta":
            reverse = True if self.order_direction == "desc" else False
            query_data = sorted(
                list(query_data), key=lambda x: (x["delta_percent"] is None, x["delta_percent"]), reverse=reverse
            )
        return query_data
