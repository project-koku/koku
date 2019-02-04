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
from collections import OrderedDict, defaultdict
from decimal import Decimal, DivisionByZero, InvalidOperation
from itertools import groupby
from urllib.parse import quote_plus

from django.db.models import CharField, F, Max, Q, Sum, Value
from django.db.models.expressions import OrderBy, RawSQL
from django.db.models.functions import Coalesce

from api.query_filter import QueryFilter, QueryFilterCollection
from api.query_handler import QueryHandler
from reporting.models import (AWSCostEntryLineItemAggregates,
                              AWSCostEntryLineItemDailySummary,
                              OCPUsageLineItemAggregates,
                              OCPUsageLineItemDailySummary)

LOG = logging.getLogger(__name__)


def strip_tag_prefix(tag):
    """Remove the query tag prefix from a tag key."""
    return tag.replace('tag:', '')


class ProviderMap(object):
    """Data structure mapping between API params and DB Model names.

    The idea here is that reports ought to be operating on largely similar
    data - counts, costs, etc. The only variable is determining which
    DB tables and fields are supplying the requested data.

    ProviderMap supplies ReportQueryHandler with the appropriate model
    references.
    """

    # main mapping data structure
    # this data should be considered static and read-only.
    mapping = [{
        'provider': 'AWS',
        'alias': 'account_alias__account_alias',
        'annotations': {'account': 'usage_account_id',
                        'service': 'product_code',
                        'az': 'availability_zone'},
        'end_date': 'usage_end',
        'filters': {
            'account': [{'field': 'account_alias__account_alias',
                        'operation': 'icontains',
                        'composition_key': 'account_filter'},
                        {'field': 'usage_account_id',
                        'operation': 'icontains',
                        'composition_key': 'account_filter'}],
            'service': {'field': 'product_code',
                        'operation': 'icontains'},
            'az': {'field': 'availability_zone',
                            'operation': 'icontains'},
            'region': {'field': 'region',
                        'operation': 'icontains'}
        },
        'tag_column': 'tags',
        'report_type': {
            'costs': {
                'aggregate': {'value': Sum('unblended_cost')},
                'aggregate_key': 'unblended_cost',
                'annotations': {'total': Sum('unblended_cost'),
                                'units': Coalesce(Max('currency_code'),
                                Value('USD'))
                },
                'count': None,
                'delta_key': {'total': Sum('unblended_cost')},
                'filter': {},
                'units_key': 'currency_code',
                'units_fallback': 'USD',
                'sum_columns': ['total'],
                'default_ordering': {'total': 'desc'},
            },
            'instance_type': {
                'aggregate': {
                    'cost': Sum('unblended_cost'),
                    'count': Sum('resource_count'),
                    'value': Sum('usage_amount'),
                },
                'aggregate_key': 'usage_amount',
                'annotations': {'cost': Sum('unblended_cost'),
                                # The summary table already already has counts
                                'count': Sum('resource_count'),
                                'total': Sum('usage_amount'),
                                'units': Coalesce(Max('unit'),
                                Value('Hrs'))},
                'count': 'resource_count',
                'delta_key': {'total': Sum('usage_amount')},
                'filter': {
                    'field': 'instance_type',
                    'operation': 'isnull',
                    'parameter': False
                },
                'group_by': ['instance_type'],
                'units_key': 'unit',
                'units_fallback': 'Hrs',
                'sum_columns': ['total', 'cost', 'count'],
                'default_ordering': {'total': 'desc'},
            },
            'storage': {
                'aggregate': {
                    'value': Sum('usage_amount'),
                    'cost': Sum('unblended_cost')
                },
                'aggregate_key': 'usage_amount',
                'annotations': {'cost': Sum('unblended_cost'),
                                'total': Sum('usage_amount'),
                                'units': Coalesce(Max('unit'),
                                Value('GB-Mo'))},
                'count': None,
                'delta_key': {'total': Sum('usage_amount')},
                'filter': {
                    'field': 'product_family',
                    'operation': 'contains',
                    'parameter': 'Storage'
                },
                'units_key': 'unit',
                'units_fallback': 'GB-Mo',
                'sum_columns': ['total', 'cost'],
                'default_ordering': {'total': 'desc'},
            },
        },
        'start_date': 'usage_start',
        'tables': {'previous_query': AWSCostEntryLineItemDailySummary,
                    'query': AWSCostEntryLineItemDailySummary,
                    'total': AWSCostEntryLineItemAggregates},
    }, {
        'provider': 'OCP',
        'annotations': {'cluster': 'cluster_id',
                        'project': 'namespace'},
        'end_date': 'usage_end',
        'filters': {
            'project': {'field': 'namespace',
                        'operation': 'icontains'},
            'cluster': [{'field': 'cluster_alias',
                        'operation': 'icontains',
                        'composition_key': 'cluster_filter'},
                        {'field': 'cluster_id',
                        'operation': 'icontains',
                        'composition_key': 'cluster_filter'}],
            'pod': {'field': 'pod',
                    'operation': 'icontains'},
            'node': {'field': 'node',
                        'operation': 'icontains'},
        },
        'tag_column': 'pod_labels',
        'report_type': {
            'charge': {
                'aggregates': {
                    'charge': Sum(F('pod_charge_cpu_core_hours') + F('pod_charge_memory_gigabyte_hours'))
                },
                'default_ordering': {'charge': 'desc'},
                'annotations': {

                    'charge': Sum(F('pod_charge_cpu_core_hours') + F('pod_charge_memory_gigabyte_hours')),
                    'units': Value('USD', output_field=CharField())
                },
                'capacity_aggregate': {},
                'delta_key': {
                    'charge': Sum(
                        F('pod_charge_cpu_core_hours') +  # noqa: W504
                        F('pod_charge_memory_gigabyte_hours')
                    )
                },
                'filter': {},
                'units_key': 'USD',
                'sum_columns': ['charge'],
            },
            'cpu': {
                'aggregates': {
                    'usage': Sum('pod_usage_cpu_core_hours'),
                    'request': Sum('pod_request_cpu_core_hours'),
                    'limit': Sum('pod_limit_cpu_core_hours'),
                    'charge': Sum('pod_charge_cpu_core_hours')
                },
                'capacity_aggregate': {
                    'capacity': Max('cluster_capacity_cpu_core_hours')
                },
                'default_ordering': {'usage': 'desc'},
                'annotations': {
                    'usage': Sum('pod_usage_cpu_core_hours'),
                    'request': Sum('pod_request_cpu_core_hours'),
                    'limit': Sum('pod_limit_cpu_core_hours'),
                    'capacity': Max('cluster_capacity_cpu_core_hours'),
                    'charge': Sum('pod_charge_cpu_core_hours'),
                    'units': Value('Core-Hours', output_field=CharField())
                },
                'delta_key': {
                    'usage': Sum('pod_usage_cpu_core_hours'),
                    'request': Sum('pod_request_cpu_core_hours'),
                    'charge': Sum('pod_charge_cpu_core_hours')
                },
                'filter': {},
                'units_key': 'Core-Hours',
                'sum_columns': ['usage', 'request', 'limit', 'charge'],
            },
            'mem': {
                'aggregates': {
                    'usage': Sum('pod_usage_memory_gigabyte_hours'),
                    'request': Sum('pod_request_memory_gigabyte_hours'),
                    'limit': Sum('pod_limit_memory_gigabyte_hours'),
                    'charge': Sum('pod_charge_memory_gigabyte_hours')
                },
                'capacity_aggregate': {
                    'capacity': Max('cluster_capacity_memory_gigabyte_hours')
                },
                'default_ordering': {'usage': 'desc'},
                'annotations': {
                    'usage': Sum('pod_usage_memory_gigabyte_hours'),
                    'request': Sum('pod_request_memory_gigabyte_hours'),
                    'limit': Sum('pod_limit_memory_gigabyte_hours'),
                    'capacity': Max('cluster_capacity_memory_gigabyte_hours'),
                    'charge': Sum('pod_charge_memory_gigabyte_hours'),
                    'units': Value('GB-Hours', output_field=CharField())
                },
                'delta_key': {
                    'usage': Sum('pod_usage_memory_gigabyte_hours'),
                    'request': Sum('pod_request_memory_gigabyte_hours'),
                    'charge': Sum('pod_charge_memory_gigabyte_hours')
                },
                'filter': {},
                'units_key': 'GB-Hours',
                'sum_columns': ['usage', 'request', 'limit', 'charge'],
            }
        },
        'start_date': 'usage_start',
        'tables': {'previous_query': OCPUsageLineItemDailySummary,
                    'query': OCPUsageLineItemDailySummary,
                    'total': OCPUsageLineItemAggregates},
    }]

    @staticmethod
    def provider_data(provider):
        """Return provider portion of map structure."""
        for item in ProviderMap.mapping:
            if provider in item.get('provider'):
                return item

    @staticmethod
    def report_type_data(report_type, provider):
        """Return report_type portion of map structure."""
        prov = ProviderMap.provider_data(provider)
        return prov.get('report_type').get(report_type)

    def __init__(self, provider, report_type):
        """Constructor."""
        self._provider = provider
        self._report_type = report_type

        self._map = ProviderMap.mapping
        self._provider_map = ProviderMap.provider_data(provider)
        self._report_type_map = ProviderMap.report_type_data(report_type, provider)

    @property
    def count(self):
        """Return the count property."""
        return self._report_type_map.get('count')

    @property
    def units_key(self):
        """Return the units_key property."""
        return self._report_type_map.get('units_key')

    @property
    def sum_columns(self):
        """Return the sum column list for the report type."""
        return self._report_type_map.get('sum_columns')


class ReportQueryHandler(QueryHandler):
    """Handles report queries and responses."""

    def __init__(self, query_parameters, url_data,
                 tenant, group_by_options, **kwargs):
        """Establish report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        LOG.debug(f'Query Params: {query_parameters}')
        self._accept_type = None
        self._group_by = None
        self._tag_keys = []
        self._no_tag_query = kwargs.get('no_tag_query')
        if kwargs:
            # view parameters
            elements = ['accept_type', 'delta', 'report_type', 'tag_keys']
            for key, value in kwargs.items():
                if key in elements:
                    setattr(self, f'_{key}', value)

        assert getattr(self, '_report_type'), \
            'kwargs["report_type"] is missing!'
        self._mapper = ProviderMap(provider=kwargs.get('provider'),
                                   report_type=self._report_type)
        default_ordering = self._mapper._report_type_map.get('default_ordering')

        super().__init__(query_parameters, url_data,
                         tenant, default_ordering, **kwargs)

        self.group_by_options = group_by_options

        self._delta = self.query_parameters.get('delta')
        self._limit = self.get_query_param_data('filter', 'limit')
        self.query_delta = {'value': None, 'percent': None}

        self.query_filter = self._get_filter()
        self.query_exclusions = self._get_exclusions()

    def get_tag_filter_keys(self):
        """Get tag keys from filter arguments."""
        tag_filters = []
        filters = self.query_parameters.get('filter', {})
        for filt in filters:
            if filt in self._tag_keys:
                tag_filters.append(filt)
        return tag_filters

    def get_tag_group_by_keys(self):
        """Get tag keys from group by arguments."""
        tag_groups = []
        filters = self.query_parameters.get('group_by', {})
        for filt in filters:
            if filt in self._tag_keys:
                tag_groups.append(filt)
        return tag_groups

    def _get_search_filter(self, filters):
        """Populate the query filter collection for search filters.

        Args:
            filters (QueryFilterCollection): collection of query filters
        Returns:
            (QueryFilterCollection): populated collection of query filters
        """
        # define filter parameters using API query params.
        fields = self._mapper._provider_map.get('filters')
        for q_param, filt in fields.items():
            group_by = self.get_query_param_data('group_by', q_param, list())
            filter_ = self.get_query_param_data('filter', q_param, list())
            list_ = list(set(group_by + filter_))    # uniquify the list
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                if isinstance(filt, list):
                    for _filt in filt:
                        for item in list_:
                            q_filter = QueryFilter(parameter=item, **_filt)
                            filters.add(q_filter)
                else:
                    for item in list_:
                        q_filter = QueryFilter(parameter=item, **filt)
                        filters.add(q_filter)

        # Update filters with tag filters
        filters = self._set_tag_filters(filters)

        composed_filters = filters.compose()
        LOG.debug(f'_get_search_filter: {composed_filters}')
        return composed_filters

    def _set_tag_filters(self, filters):
        """Create tag_filters."""
        tag_column = self._mapper._provider_map.get('tag_column')
        tag_filters = self.get_tag_filter_keys()
        tag_group_by = self.get_tag_group_by_keys()
        tag_filters.extend(tag_group_by)
        if not tag_filters and self._no_tag_query:
            filters.add(self._no_tag_query)

        for tag in tag_filters:
            # Update the filter to use the label column name
            tag_db_name = tag_column + '__' + strip_tag_prefix(tag)
            filt = {
                'field': tag_db_name,
                'operation': 'icontains'
            }
            group_by = self.get_query_param_data('group_by', tag, list())
            filter_ = self.get_query_param_data('filter', tag, list())
            list_ = list(set(group_by + filter_))  # uniquify the list
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                for item in list_:
                    q_filter = QueryFilter(parameter=item, **filt)
                    filters.add(q_filter)
            elif list_ and ReportQueryHandler.has_wildcard(list_):
                wild_card_filt = {
                    'field': tag_column,
                    'operation': 'has_key'
                }
                q_filter = QueryFilter(parameter=strip_tag_prefix(tag),
                                       **wild_card_filt)
                filters.add(q_filter)
        return filters

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = super()._get_filter(delta)

        # set up filters for instance-type and storage queries.
        filters.add(**self._mapper._report_type_map.get('filter'))

        # define filter parameters using API query params.
        composed_filters = self._get_search_filter(filters)

        LOG.debug(f'_get_filter: {composed_filters}')
        return composed_filters

    def _get_exclusions(self, delta=False):
        """Create dictionary for filter parameters for exclude clause.

        Returns:
            (Dict): query filter dictionary

        """
        exclusions = QueryFilterCollection()
        tag_column = self._mapper._provider_map.get('tag_column')
        tag_group_by = self.get_tag_group_by_keys()
        if tag_group_by:
            for tag in tag_group_by:
                tag_db_name = tag_column + '__' + strip_tag_prefix(tag)
                filt = {
                    'field': tag_db_name,
                    'operation': 'isnull',
                    'parameter': True
                }
                q_filter = QueryFilter(**filt)
                exclusions.add(q_filter)

        composed_exclusions = exclusions.compose()

        LOG.debug(f'_get_exclusions: {composed_exclusions}')
        return composed_exclusions

    def _get_group_by(self):
        """Create list for group_by parameters."""
        group_by = []
        for item in self.group_by_options:
            group_data = self.get_query_param_data('group_by', item)
            if group_data:
                group_pos = self.url_data.index(item)
                group_by.append((item, group_pos))

        tag_group_by = self._get_tag_group_by()
        group_by.extend(tag_group_by)
        group_by = sorted(group_by, key=lambda g_item: g_item[1])
        group_by = [item[0] for item in group_by]

        # This is a current workaround for AWS instance-types reports
        # It is implied that limiting is performed by account/region and
        # not by instance type when those group by params are used.
        # For that ranking to work we can't also group by instance_type.
        inherent_group_by = self._mapper._report_type_map.get('group_by')
        if (inherent_group_by and not (group_by and self._limit)):
            group_by += inherent_group_by
        return group_by

    def _get_tag_group_by(self):
        """Create list of tag based group by parameters."""
        group_by = []
        tag_column = self._mapper._provider_map.get('tag_column')
        tag_groups = self.get_tag_group_by_keys()
        for tag in tag_groups:
            tag_db_name = tag_column + '__' + strip_tag_prefix(tag)
            group_data = self.get_query_param_data('group_by', tag)
            if group_data:
                tag = quote_plus(tag)
                group_pos = self.url_data.index(tag)
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
        pass

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
            grouped = ReportQueryHandler._group_data_by_list(group_by_list,
                                                             (group_index + 1),
                                                             grouped)
            datapoint = out_data.get(key)
            if datapoint and isinstance(datapoint, dict):
                out_data[key].update(grouped)
            elif datapoint and isinstance(datapoint, list):
                out_data[key] = grouped + datapoint
            else:
                out_data[key] = grouped
        return out_data

    def _apply_group_by(self, query_data, group_by=None):
        """Group data by date for given time interval then group by list.

        Args:
            query_data  (List(Dict)): Queried data
            group_by (list): An optional list of groups
        Returns:
            (Dict): Dictionary of grouped dictionaries

        """
        bucket_by_date = OrderedDict()
        for item in self.time_interval:
            date_string = self.date_to_string(item)
            bucket_by_date[date_string] = []

        for result in query_data:
            if self._limit:
                del result['rank']
            date_string = result.get('date')
            date_bucket = bucket_by_date.get(date_string)
            if date_bucket is not None:
                date_bucket.append(result)

        for date, data_list in bucket_by_date.items():
            data = data_list
            if group_by is None:
                group_by = self._get_group_by()
            grouped = ReportQueryHandler._group_data_by_list(group_by, 0,
                                                             data)
            bucket_by_date[date] = grouped
        return bucket_by_date

    def _transform_data(self, groups, group_index, data):
        """Transform dictionary data points to lists."""
        groups_len = len(groups)
        if not groups or group_index >= groups_len:
            return data

        out_data = []
        label = 'values'
        group_type = groups[group_index]
        next_group_index = (group_index + 1)

        if next_group_index < groups_len:
            label = groups[next_group_index] + 's'

        for group, group_value in data.items():
            cur = {group_type: group,
                   label: self._transform_data(groups, next_group_index,
                                               group_value)}
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
        numeric_ordering = ['date', 'rank', 'delta', 'delta_percent', 'total', 'charge', 'usage']
        sorted_data = data
        for field in reversed(order_fields):
            reverse = False
            field = field.replace('delta', 'delta_percent')
            if '-' in field:
                reverse = True
                field = field.replace('-', '')
            if field in numeric_ordering:
                sorted_data = sorted(sorted_data, key=lambda entry: entry[field],
                                     reverse=reverse)
            else:
                sorted_data = sorted(sorted_data, key=lambda entry: entry[field].lower(),
                                     reverse=reverse)
        return sorted_data

    def get_tag_order_by(self, tag):
        """Generate an OrderBy clause forcing JSON column->key to be used.

        Args:
            tag (str): The Django formatted tag string
                       Ex. pod_labels__key

        Returns:
            OrderBy: A Django OrderBy clause using raw SQL

        """
        descending = True if self.order_direction == 'desc' else False
        tag_column, tag_value = tag.split('__')
        return OrderBy(
            RawSQL(
                f'{tag_column} -> %s',
                (tag_value,)
            ),
            descending=descending
        )

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

        for date in date_grouped_data:
            other = None
            ranked_list = []
            others_list = []
            other_sums = {column: 0 for column in self._mapper.sum_columns}
            for data in date_grouped_data[date]:
                if other is None:
                    other = copy.deepcopy(data)
                rank = data.get('rank')
                if rank <= self._limit:
                    ranked_list.append(data)
                else:
                    others_list.append(data)
                    for column in self._mapper.sum_columns:
                        other_sums[column] += data.get(column) if data.get(column) else 0

            if other is not None and others_list:
                num_others = len(others_list)
                others_label = '{} Others'.format(num_others)
                if num_others == 1:
                    others_label = '{} Other'.format(num_others)
                other.update(other_sums)
                other['rank'] = self._limit + 1
                group_by = self._get_group_by()
                for group in group_by:
                    other[group] = others_label
                if 'account' in group_by:
                    other['account_alias'] = others_label
                ranked_list.append(other)
            rank_limited_data[date] = ranked_list

        return self.unpack_date_grouped_data(rank_limited_data)

    def date_group_data(self, data_list):
        """Group data by date."""
        date_grouped_data = defaultdict(list)

        for data in data_list:
            key = data.get('date')
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
        delta_field = self._mapper._report_type_map.get('delta_key').get(self._delta)
        delta_annotation = {self._delta: delta_field}
        previous_sums = previous_sums\
            .values(*query_group_by)\
            .annotate(**delta_annotation)
        previous_dict = OrderedDict()
        for row in previous_sums:
            date = self.string_to_date(row['date'])
            date = date + date_delta
            row['date'] = self.date_to_string(date)
            key = tuple((row[key] for key in query_group_by))
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
        delta_group_by = ['date'] + self._get_group_by()
        delta_filter = self._get_filter(delta=True)
        q_table = self._mapper._provider_map.get('tables').get('previous_query')
        previous_query = q_table.objects.filter(delta_filter)
        previous_dict = self._create_previous_totals(previous_query,
                                                     delta_group_by)
        for row in query_data:
            key = tuple((row[key] for key in delta_group_by))
            previous_total = previous_dict.get(key, 0)
            current_total = row.get(self._delta, 0)
            row['delta_value'] = current_total - previous_total
            row['delta_percent'] = self._percent_delta(current_total, previous_total)
        # Calculate the delta on the total aggregate
        if self._delta in query_sum:
            current_total_sum = Decimal(query_sum.get(self._delta) or 0)
        else:
            current_total_sum = Decimal(query_sum.get('value') or 0)
        delta_field = self._mapper._report_type_map.get('delta_key').get(self._delta)
        prev_total_sum = previous_query.aggregate(value=delta_field)
        if self.resolution == 'daily':
            dates = [entry.get('date') for entry in query_data]
            prev_total_filters = self._get_previous_totals_filter(dates)
            if prev_total_filters:
                prev_total_sum = previous_query\
                    .filter(prev_total_filters)\
                    .aggregate(value=delta_field)

        prev_total_sum = Decimal(prev_total_sum.get('value') or 0)

        total_delta = current_total_sum - prev_total_sum
        total_delta_percent = self._percent_delta(current_total_sum,
                                                  prev_total_sum)

        self.query_delta = {
            'value': total_delta,
            'percent': total_delta_percent
        }

        if self.order_field == 'delta':
            reverse = True if self.order_direction == 'desc' else False
            query_data = sorted(list(query_data),
                                key=lambda x: x['delta_percent'],
                                reverse=reverse)
        return query_data

    def strip_label_column_name(self, data, group_by):
        """Remove the column name from tags."""
        tag_column = self._mapper._provider_map.get('tag_column')
        val_to_strip = tag_column + '__'
        new_data = []
        for entry in data:
            new_entry = {}
            for key, value in entry.items():
                key = key.replace(val_to_strip, '')
                new_entry[key] = value

            new_data.append(new_entry)

        for i, group in enumerate(group_by):
            group_by[i] = group.replace(val_to_strip, '')

        return new_data, group_by
