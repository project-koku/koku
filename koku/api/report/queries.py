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
import datetime
import re
from collections import OrderedDict
from decimal import Decimal, DivisionByZero
from itertools import groupby

from django.db.models import (F,
                              Sum,
                              Value,
                              Window)
from django.db.models.functions import (Concat,
                                        DenseRank,
                                        TruncDay,
                                        TruncMonth)
from tenant_schemas.utils import tenant_context

from api.utils import DateHelper
from reporting.models import (AWSAccountAlias,
                              AWSCostEntryLineItem,
                              AWSCostEntryLineItemAggregates,
                              AWSCostEntryLineItemDailySummary)


WILDCARD = '*'
OPERATION_SUM = 'sum'
OPERATION_NONE = 'none'
EXPORT_COLUMNS = ['cost_entry_id', 'cost_entry_bill_id',
                  'cost_entry_product_id', 'cost_entry_pricing_id',
                  'cost_entry_reservation_id', 'tags',
                  'invoice_id', 'line_item_type', 'usage_account_id',
                  'usage_start', 'usage_end', 'product_code',
                  'usage_type', 'operation', 'availability_zone',
                  'usage_amount', 'normalization_factor',
                  'normalized_usage_amount', 'currency_code',
                  'unblended_rate', 'unblended_cost', 'blended_rate',
                  'blended_cost', 'tax_type']


class TruncDayString(TruncDay):
    """Class to handle string formated day truncation."""

    def convert_value(self, value, expression, connection):
        """Convert value to a string after super."""
        value = super().convert_value(value, expression, connection)
        return value.strftime('%Y-%m-%d')


class TruncMonthString(TruncMonth):
    """Class to handle string formated day truncation."""

    def convert_value(self, value, expression, connection):
        """Convert value to a string after super."""
        value = super().convert_value(value, expression, connection)
        return value.strftime('%Y-%m')


class ReportQueryHandler(object):
    """Handles report queries and responses."""

    default_ordering = {'total': 'desc'}

    def __init__(self, query_parameters, url_data,
                 tenant, aggregate_key, units_key, **kwargs):
        """Establish report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            aggregate_key   (String): the key to aggregate on
            units_key   (String): the key defining the units
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        self._accept_type = None
        self._annotations = None
        self._count = None
        self._filter = None
        self._group_by = None
        self.end_datetime = None
        self.resolution = None
        self.start_datetime = None
        self.time_interval = []
        self.time_scope_units = None
        self.time_scope_value = None

        self.aggregate_key = aggregate_key
        self.query_parameters = query_parameters
        self.tenant = tenant
        self.url_data = url_data

        self.operation = self.query_parameters.get('operation', OPERATION_SUM)
        self._delta = self.query_parameters.get('delta')
        self._limit = self.get_query_param_data('filter', 'limit')
        self._get_timeframe()
        self.units_key = units_key

        self.account_aliases = {}

        if kwargs:
            elements = ['accept_type', 'annotations', 'delta',
                        'filter', 'group_by', 'report_type']
            for key, value in kwargs.items():
                if key in elements:
                    setattr(self, f'_{key}', value)

            # don't override the property by using setattr
            if 'count' in kwargs:
                self.count = kwargs['count']

        assert getattr(self, '_report_type'), \
            'kwargs["report_type"] is missing!'

    @property
    def is_sum(self):
        """Determine the type of API call this is.

        is_sum == True -> API Summary data
        is_sum == False -> Full data download

        """
        return self.operation == OPERATION_SUM

    @property
    def units_key(self):
        """Return the unit used in this query."""
        return self._units_key

    @units_key.setter
    def units_key(self, value):
        """Set the units_key."""
        self._units_key = value
        if self.is_sum:
            self._units_key = value.replace('cost_entry_pricing__', '')

    @property
    def count(self):
        """Return the count property."""
        return self._count

    @count.setter
    def count(self, value):
        """Set the count property."""
        self._count = value
        if self.is_sum:
            self._count = 'resource_count'

    @property
    def join_tables(self):
        """List the foreign tables line items join to."""
        return [
            'cost_entry_product',
            'cost_entry_pricing',
            'cost_entry_reservation'
        ]

    @staticmethod
    def has_wildcard(in_list):
        """Check if list has wildcard.

        Args:
            in_list (List[String]): List of strings to check for wildcard
        Return:
            (Boolean): if wildcard is present in list
        """
        if not in_list:
            return False
        return any(WILDCARD == item for item in in_list)

    def check_query_params(self, key, in_key):
        """Test if query parameters has a given key and key within it.

        Args:
        key     (String): key to check in query parameters
        in_key  (String): key to check if key is found in query parameters

        Returns:
            (Boolean): True if they keys given appear in given query parameters.

        """
        return (self.query_parameters and key in self.query_parameters and
                in_key in self.query_parameters.get(key))

    def get_query_param_data(self, dictkey, key, default=None):
        """Extract the value from a query parameter dictionary or return None.

        Args:
            dictkey (String): the key to access a query parameter dictionary
            key     (String): the key to obtain from the dictionar data
        Returns:
            (Object): The value found with the given key or the default value
        """
        value = default
        if self.check_query_params(dictkey, key):
            value = self.query_parameters.get(dictkey).get(key)
        return value

    @property
    def order_field(self):
        """Order-by field name.

        The default is 'total'
        """
        order_by = self.query_parameters.get('order_by', self.default_ordering)
        return list(order_by.keys()).pop()

    @property
    def order_direction(self):
        """Order-by orientation value.

        Returns:
            (str) 'asc' or 'desc'; default is 'desc'

        """
        order_by = self.query_parameters.get('order_by', self.default_ordering)
        return list(order_by.values()).pop()

    @property
    def order(self):
        """Extract order_by parameter and apply ordering to the appropriate field.

        Returns:
            (String): Ordering value. Default is '-total'

        Example:
            `order_by[total]=asc` returns `total`
            `order_by[total]=desc` returns `-total`

        """
        order_map = {'asc': '', 'desc': '-'}
        return f'{order_map[self.order_direction]}{self.order_field}'

    def get_resolution(self):
        """Extract resolution or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        if self.resolution:
            return self.resolution

        self.resolution = self.get_query_param_data('filter', 'resolution')
        time_scope_value = self.get_time_scope_value()
        if not self.resolution:
            self.resolution = 'daily'
            if int(time_scope_value) in [-1, -2]:
                self.resolution = 'monthly'

        if self.resolution == 'monthly':
            self.date_to_string = lambda dt: dt.strftime('%Y-%m')
            self.date_trunc = TruncMonthString
            self.gen_time_interval = DateHelper().list_months
        else:
            self.date_to_string = lambda dt: dt.strftime('%Y-%m-%d')
            self.date_trunc = TruncDayString
            self.gen_time_interval = DateHelper().list_days

        return self.resolution

    def get_time_scope_units(self):
        """Extract time scope units or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        if self.time_scope_units:
            return self.time_scope_units

        time_scope_units = self.get_query_param_data('filter', 'time_scope_units')
        time_scope_value = self.get_query_param_data('filter', 'time_scope_value')
        if not time_scope_units:
            time_scope_units = 'day'
            if time_scope_value and int(time_scope_value) in [-1, -2]:
                time_scope_units = 'month'

        self.time_scope_units = time_scope_units
        return self.time_scope_units

    def get_time_scope_value(self):
        """Extract time scope value or provide default.

        Returns:
            (Integer): time relative value providing query scope

        """
        if self.time_scope_value:
            return self.time_scope_value

        time_scope_units = self.get_query_param_data('filter', 'time_scope_units')
        time_scope_value = self.get_query_param_data('filter', 'time_scope_value')

        if not time_scope_value:
            time_scope_value = -10
            if time_scope_units == 'month':
                time_scope_value = -1

        self.time_scope_value = int(time_scope_value)
        return self.time_scope_value

    def _create_time_interval(self):
        """Create list of date times in interval.

        Returns:
            (List[DateTime]): List of all interval slices by resolution

        """
        self.time_interval = sorted(self.gen_time_interval(
            self.start_datetime,
            self.end_datetime))
        return self.time_interval

    def _get_timeframe(self):
        """Obtain timeframe start and end dates.

        Returns:
            (DateTime): start datetime for query filter
            (DateTime): end datetime for query filter

        """
        self.get_resolution()
        time_scope_value = self.get_time_scope_value()
        time_scope_units = self.get_time_scope_units()
        start = None
        end = None
        dh = DateHelper()
        if time_scope_units == 'month':
            if time_scope_value == -1:
                # get current month
                start = dh.this_month_start
                end = dh.this_month_end
            else:
                # get previous month
                start = dh.last_month_start
                end = dh.last_month_end
        else:
            if time_scope_value == -10:
                # get last 10 days
                start = dh.n_days_ago(dh.this_hour, 10)
                end = dh.this_hour
            else:
                # get last 30 days
                start = dh.n_days_ago(dh.this_hour, 30)
                end = dh.this_hour

        self.start_datetime = start
        self.end_datetime = end
        self._create_time_interval()
        return (self.start_datetime, self.end_datetime, self.time_interval)

    def _get_filter(self):
        """Create dictionary for filter parameters.

        Returns:
            (Dict): query filter dictionary

        """
        filter_dict = {
            'usage_start__gte': self.start_datetime,
            'usage_end__lte': self.end_datetime,
        }
        if self.is_sum:
            # Summary table is already wrapped up at the date level
            filter_dict = {
                'usage_start__gte': self.start_datetime.date(),
                'usage_start__lte': self.end_datetime.date(),
            }
        if self._filter:
            filter_dict.update(self._filter)

        # { query_param: database_field_name }
        fields = {'account': 'usage_account_id',
                  'service': 'product_code',
                  'region': 'cost_entry_product__region',
                  'avail_zone': 'availability_zone'}
        if self.is_sum:
            # Use the summary table that has region built in
            fields.update({'region': 'region'})
        # db query operation
        op = 'in'
        for q_param, db_field in fields.items():
            group_by = self.get_query_param_data('group_by', q_param, list())
            filter_ = self.get_query_param_data('filter', q_param, list())
            list_ = list(set(group_by + filter_))    # uniquify the list
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                filter_dict[f'{db_field}__{op}'] = list_

        return filter_dict

    def _strip_table_references(self, filters):
        """Remove the foreign table reference from a Django query string.

        Args:
            filter (dict): The Django query filter dict

        Returns:
            (dict): The query filter with the table reference stripped

        """
        filters = copy.deepcopy(filters)
        for key in filters:
            for table_name in self.join_tables:
                if table_name in key:
                    new_key = key.replace(f'{table_name}__', '')
                    filters[new_key] = filters[key]
                    filters.pop(key, None)
        return filters

    def _get_group_by(self):
        """Create list for group_by parameters."""
        group_by = []
        group_by_options = ['service', 'account', 'region', 'avail_zone']
        for item in group_by_options:
            group_data = self.get_query_param_data('group_by', item)
            if group_data:
                group_pos = self.url_data.index(item)
                group_by.append((item, group_pos))

        group_by = sorted(group_by, key=lambda g_item: g_item[1])
        group_by = [item[0] for item in group_by]
        if self._group_by:
            group_by += self._group_by
        return group_by

    def _get_annotations(self, fields=None):
        """Create dictionary for query annotations.

        Args:
            fields (dict): Fields to create annotations for

        Returns:
            (Dict): query annotations dictionary

        """
        annotations = {
            'date': self.date_trunc('usage_start'),
            'units': Concat(self.units_key, Value(''))
        }
        if self._annotations and not self.is_sum:
            annotations.update(self._annotations)

        # { query_param: database_field_name }
        if not fields:
            fields = {'account': 'usage_account_id',
                      'service': 'product_code',
                      'region': 'cost_entry_product__region',
                      'avail_zone': 'availability_zone'}
            if self.is_sum:
                # The summary table has region built in
                fields.pop('region', None)
        for q_param, db_field in fields.items():
            annotations[q_param] = Concat(db_field, Value(''))

        return annotations

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

    def _ranked_list(self, data_list):
        """Get list of ranked items less than top.

        Args:
            data_list (List(Dict)): List of ranked data points from the same bucket
        Returns:
            List(Dict): List of data points meeting the rank criteria
        """
        ranked_list = []
        others_list = []
        other = None
        other_sum = 0
        for data in data_list:
            if other is None:
                other = copy.deepcopy(data)
            rank = data.get('rank')
            if rank <= self._limit:
                del data['rank']
                ranked_list.append(data)
            else:
                others_list.append(data)
                total = data.get('total')
                if total:
                    other_sum += total

        if other is not None and others_list:
            other['total'] = other_sum
            del other['rank']
            group_by = self._get_group_by()
            for group in group_by:
                other[group] = 'Other'
            ranked_list.append(other)

        return ranked_list

    def _apply_group_by(self, query_data):
        """Group data by date for given time interval then group by list.

        Args:
            query_data  (List(Dict)): Queried data
        Returns:
            (Dict): Dictionary of grouped dictionaries

        """
        bucket_by_date = OrderedDict()
        for item in self.time_interval:
            date_string = self.date_to_string(item)
            bucket_by_date[date_string] = []

        for result in query_data:
            date_string = result.get('date')
            date_bucket = bucket_by_date.get(date_string)
            if date_bucket is not None:
                date_bucket.append(result)

        for date, data_list in bucket_by_date.items():
            data = data_list
            if self._limit:
                data = self._ranked_list(data_list)
            group_by = self._get_group_by()
            grouped = ReportQueryHandler._group_data_by_list(group_by, 0,
                                                             data)
            bucket_by_date[date] = grouped
        return bucket_by_date

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = copy.deepcopy(self.query_parameters)
        output['data'] = self.query_data
        output['total'] = self.query_sum

        if self._delta:
            output['delta'] = self.query_delta

        return output

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
            if group_type == 'account':
                for value in group_value:
                    if isinstance(value, dict):
                        account_id = value.get('account')
                        alias = self.account_aliases.get(str(account_id))
                        if alias:
                            value['account_alias'] = alias

            out_data.append(cur)

        return out_data

    def execute_query(self):    # noqa: C901
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = {'value': 0}
        data = []

        with tenant_context(self.tenant):
            query_filter = self._get_filter()
            query_group_by = self._get_group_by()
            query_annotations = self._get_annotations()
            query_order_by = ('-date',)

            if self.is_sum:
                query_filter = self._strip_table_references(query_filter)
                query = AWSCostEntryLineItemDailySummary.objects.filter(
                    **query_filter
                )
            else:
                query = AWSCostEntryLineItem.objects.filter(
                    **query_filter
                )
            query_data = query.annotate(**query_annotations)
            query_group_by = ['date'] + query_group_by
            query_group_by_with_units = query_group_by + ['units']

            if self.is_sum:
                query_order_by += (self.order,)
                query_data = query_data.values(*query_group_by_with_units)\
                    .annotate(total=Sum(self.aggregate_key))

            if self.count and self.is_sum:
                # This is a sum because the summary table already
                # has already performed counts
                query_data = query_data.annotate(
                    count=Sum(self.count)
                )

            if self._limit and self.is_sum:
                rank_order = getattr(F(self.order_field), self.order_direction)()
                dense_rank_by_total = Window(
                    expression=DenseRank(),
                    partition_by=F('date'),
                    order_by=rank_order
                )
                query_data = query_data.annotate(rank=dense_rank_by_total)
                query_order_by = query_order_by + ('rank',)

            for alias in AWSAccountAlias.objects.all():
                self.account_aliases[alias.account_id] = alias.account_alias

            query_data = query_data.order_by(*query_order_by)
            is_csv_output = self._accept_type and 'text/csv' in self._accept_type
            if self.is_sum and not is_csv_output:
                data = self._apply_group_by(list(query_data))
                data = self._transform_data(query_group_by, 0, data)
            elif is_csv_output and self.is_sum:
                values_out = query_group_by_with_units + ['total']
                if self._limit:
                    data = self._ranked_list(list(query_data))
                else:
                    data = list(query_data)
            else:
                values_out = query_group_by_with_units + EXPORT_COLUMNS
                data = list(query_data.values(*values_out))

            if query.exists():
                units_value = query.values(self.units_key).first().get(self.units_key)
                query_sum = self.calculate_total(units_value)

            if self._delta:
                self.query_delta = self.calculate_delta(self._delta,
                                                        query,
                                                        query_sum,
                                                        **query_filter)

        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()

    def calculate_delta(self, delta, query, query_sum, **kwargs):
        """Calculate cost deltas.

        Args:
            delta (String) 'day', 'month', or 'year'
            query (Query) the original query being compared

        Returns:
            (dict) with keys "value" and "percent"

        """
        delta_filter = copy.deepcopy(kwargs)

        # get delta date range
        _start = kwargs.get('usage_start__gte')
        _end = kwargs.get('usage_end__lte')
        if self.is_sum:
            # Override as summary table is date based, not timestamp
            _end = kwargs.get('usage_start__lte')

        if delta == 'day':
            previous = datetime.timedelta(days=1)
        elif delta == 'month':
            dh = DateHelper()
            last_month = dh.days_in_month(_start.replace(day=1) - dh.one_day)
            previous = datetime.timedelta(days=last_month)
        elif delta == 'year':
            previous = datetime.timedelta(days=365)
        else:
            # paranoia.
            raise NotImplementedError(f'invalid parameter: {delta}')

        delta_filter['usage_start__gte'] = _start - previous

        if self.is_sum:
            delta_filter['usage_start__lte'] = _end - previous
            # construct new query
            delta_query = AWSCostEntryLineItemDailySummary.objects.filter(
                **delta_filter
            )
        else:
            delta_filter['usage_end__lte'] = _end - previous
            delta_query = AWSCostEntryLineItem.objects.filter(**delta_filter)

        # get aggregate sum from query
        delta_sum = delta_query.aggregate(value=Sum(self.aggregate_key))

        # calculate percentage difference: ((total - delta_total) / delta_total * 100)
        q_sum = Decimal(query_sum.get('value') or 0)
        d_sum = Decimal(delta_sum.get('value') or 0)
        d_value = q_sum - d_sum

        try:
            d_percent = (q_sum - d_sum) / d_sum * Decimal(100)
        except DivisionByZero:
            d_percent = Decimal(0)

        query_delta = {'value': d_value, 'percent': d_percent}
        return query_delta

    def calculate_total(self, units_value):
        """Calculate aggregated totals for the query.

        Args:
            units_value (str): The unit of the reported total

        Returns:
            (dict) The aggregated totals for the query

        """
        filter_fields = [
            'availability_zone',
            'region',
            'usage_account_id',
            'product_code'
        ]
        total_filter = {}
        query_filter = self._get_filter()

        for field in filter_fields:
            total_filter.update(
                {key: value for key, value in query_filter.items()
                 if re.match(field, key)}
            )

        total_filter['time_scope_value'] = self.get_query_param_data(
            'filter',
            'time_scope_value',
            0
        )
        total_filter['report_type'] = self._report_type
        total_query = AWSCostEntryLineItemAggregates.objects.filter(
            **total_filter
        )
        if self.count:
            query_sum = total_query.aggregate(
                value=Sum(self.aggregate_key),
                # This is a sum because the summary table already
                # has already performed counts
                count=Sum(self.count)
            )
        else:
            query_sum = total_query.aggregate(value=Sum(self.aggregate_key))
        query_sum['units'] = units_value

        return query_sum
