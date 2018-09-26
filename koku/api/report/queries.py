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
import logging
import re
from collections import OrderedDict, UserDict
from decimal import Decimal, DivisionByZero, InvalidOperation
from itertools import groupby

from dateutil import relativedelta
from django.db.models import (F,
                              Max,
                              Sum,
                              Value,
                              Window)
from django.db.models.functions import (Concat,
                                        DenseRank,
                                        TruncDay,
                                        TruncMonth)
from tenant_schemas.utils import tenant_context

from api.utils import DateHelper
from reporting.models import (AWSCostEntryLineItem,
                              AWSCostEntryLineItemAggregates,
                              AWSCostEntryLineItemDailySummary)


logging.disable(0)
LOG = logging.getLogger(__name__)
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


class QueryFilter(UserDict):
    """Dict-like object representing a single query filter."""

    SEP = '__'    # separator
    table = None
    field = None
    operation = None
    parameter = None

    def __init__(self, table=None, field=None, operation=None, parameter=None):
        """Constructor.

        Args:
            table (str) - The name of a DB table
            field (str) - The name of a DB field
            operation (str) - The name of a DB operation, e.g. 'in' or 'gte'
            parameter (object) - A valid query target, e.g. a list or datetime
        """
        super().__init__(table=table, field=field, operation=operation,
                         parameter=parameter)
        self.table = table
        self.field = field
        self.operation = operation
        self.parameter = parameter

    def composed_query_string(self):
        """Return compiled query string."""
        fields = [entry for entry in [self.table, self.field, self.operation]
                  if entry is not None]
        return self.SEP.join(fields)

    def composed_dict(self):
        """Return a dict formatted for Django's ORM."""
        return {self.composed_query_string(): self.parameter}

    def from_string(self, query_string):
        """Parse a string representing a filter.

        Returns:
            QueryFilter instance.

        Args:
            query_string (str) A string representing a query filter.

        Example:
            QueryFilter().from_string('mytable__myfield__contains')

        """
        parts = query_string.split(self.SEP)
        if len(parts) == 3:
            self.table, self.field, self.operation = parts
        elif len(parts) == 2:
            self.table, self.operation = parts
        else:
            message = 'Incorrect number of parts in query string. ' + \
                'Need at least two of [table, field, operation].'
            raise TypeError(message)
        return self

    def __repr__(self):
        """Return string representation."""
        return str(self.composed_dict())


class QueryFilterCollection(object):
    """Object representing a set of filters for a query."""

    def __init__(self, filters=None):
        """Constructor."""
        if filters is None:
            self._filters = list()    # a list of QueryFilter objects
        else:
            for item in filters:
                if not isinstance(item, QueryFilter):
                    message = 'Filters list must be instances of QueryFilter.'
                    raise TypeError(message)
            self._filters = filters

    def add(self, query_filter=None, table=None, field=None, operation=None, parameter=None):
        """Add a query filter to the collection.

        Args:
            query_filter (QueryFilter) a QueryFilter object

            - or -

            table (str)  db table name
            field (str)  db field/row name
            operation (str) db operation
            parameter (object) query object

        """
        error_message = 'query_filter can not be defined with other parameters'
        if query_filter and (table or field or operation or parameter):
            raise AttributeError(error_message)

        if query_filter:
            self._filters.append(query_filter)

        if (table or field or operation or parameter):
            qf = QueryFilter(table=table, field=field, operation=operation,
                             parameter=parameter)
            self._filters.append(qf)

    def compose(self):
        """Compose filters into a dict for submitting to Django's ORM."""
        out = {}
        for filt in self._filters:
            if filt.parameter is not None:
                out.update(filt.composed_dict())
        return out

    def __repr__(self):
        """Return string representation."""
        out = f'{self.__class__}: '
        for filt in self._filters:
            out += filt.__repr__() + ', '
        return out


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
        LOG.debug(f'Query Params: {query_parameters}')

        self._accept_type = None
        self._annotations = None
        self._count = None
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
        self.query_delta = {'value': None, 'percent': None}

        if kwargs:
            elements = ['accept_type', 'annotations', 'delta',
                        'group_by', 'report_type']
            for key, value in kwargs.items():
                if key in elements:
                    setattr(self, f'_{key}', value)

            # don't override the property by using setattr
            if 'count' in kwargs:
                self.count = kwargs['count']

        self.query_filter = self._get_filter()

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
            self.string_to_date = lambda dt: datetime.datetime.strptime(dt, '%Y-%m').date()
            self.date_trunc = TruncMonthString
            self.gen_time_interval = DateHelper().list_months
        else:
            self.date_to_string = lambda dt: dt.strftime('%Y-%m-%d')
            self.string_to_date = lambda dt: datetime.datetime.strptime(dt, '%Y-%m-%d').date()
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
        filters = QueryFilterCollection()

        # the summary table mirrors many of the fields in the cost_entry_product table.
        cep_table = 'cost_entry_product'
        if self.is_sum:
            cep_table = None

        # set up filters for instance-type and storage queries.
        if self._report_type == 'instance_type':
            filters.add(table=cep_table, field='instance_type',
                        operation='isnull', parameter=False)
        elif self._report_type == 'storage':
            filters.add(table=cep_table, field='product_family',
                        operation='contains', parameter='Storage')

        region_filter = QueryFilter(table=cep_table, field='region', operation='in')

        start_filter = QueryFilter(table='usage_start', operation='gte',
                                   parameter=self.start_datetime)
        end_filter = QueryFilter(table='usage_end', operation='lte',
                                 parameter=self.end_datetime)
        filters.add(query_filter=start_filter)
        filters.add(query_filter=end_filter)

        # define filter parameters using API query params.
        fields = {'account': QueryFilter(field='usage_account_id',
                                         operation='in'),
                  'service': QueryFilter(field='product_code', operation='in'),
                  'region': region_filter,
                  'avail_zone': QueryFilter(field='availability_zone',
                                            operation='in')}
        for q_param, filt in fields.items():
            group_by = self.get_query_param_data('group_by', q_param, list())
            filter_ = self.get_query_param_data('filter', q_param, list())
            list_ = list(set(group_by + filter_))    # uniquify the list
            if list_ and not ReportQueryHandler.has_wildcard(list_):
                filt.parameter = list_
            filters.add(filt)

        LOG.debug(f'Filters: {filters.compose()}')
        return filters.compose()

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
                      'avail_zone': 'availability_zone'}

            if not self.is_sum:
                # The summary table has region built-in
                fields['region'] = 'cost_entry_product__region'

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
            out_data.append(cur)

        return out_data

    def execute_sum_query(self):
        """Execute query and return provided data when self.is_sum == True.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = {'value': 0}
        data = []

        with tenant_context(self.tenant):
            query = AWSCostEntryLineItemDailySummary.objects.filter(**self.query_filter)

            query_annotations = self._get_annotations()
            query_data = query.annotate(**query_annotations)

            query_group_by = ['date'] + self._get_group_by()

            query_order_by = ('-date', )
            if self.order_field != 'delta':
                query_order_by += (self.order,)

            query_data = query_data.values(*query_group_by)\
                .annotate(total=Sum(self.aggregate_key))\
                .annotate(units=Max(self.units_key))\
                .annotate(account_alias=Concat('account_alias__account_alias',
                                               Value('')))

            if self.count:
                # This is a sum because the summary table already
                # has already performed counts
                query_data = query_data.annotate(count=Sum(self.count))

            if self._limit:
                rank_order = getattr(F(self.order_field), self.order_direction)()
                dense_rank_by_total = Window(
                    expression=DenseRank(),
                    partition_by=F('date'),
                    order_by=rank_order
                )
                query_data = query_data.annotate(rank=dense_rank_by_total)
                query_order_by = query_order_by + ('rank',)

            if self.order_field != 'delta':
                query_data = query_data.order_by(*query_order_by)

            if query.exists():
                units_value = query.values(self.units_key).first().get(self.units_key)
                query_sum = self.calculate_total(units_value)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            is_csv_output = self._accept_type and 'text/csv' in self._accept_type
            if is_csv_output:
                if self._limit:
                    data = self._ranked_list(list(query_data))
                else:
                    data = list(query_data)
            else:
                data = self._apply_group_by(list(query_data))
                data = self._transform_data(query_group_by, 0, data)

        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        if self.is_sum:
            return self.execute_sum_query()

        query_sum = {'value': 0}
        data = []

        with tenant_context(self.tenant):
            query = AWSCostEntryLineItem.objects.filter(**self.query_filter)

            query_annotations = self._get_annotations()
            query_data = query.annotate(**query_annotations)

            query_group_by = ['date'] + self._get_group_by()
            query_group_by_with_units = query_group_by + ['units']

            query_order_by = ('-date',)
            query_data = query_data.order_by(*query_order_by)
            values_out = query_group_by_with_units + EXPORT_COLUMNS
            data = list(query_data.values(*values_out))

            if query.exists():
                units_value = query.values(self.units_key).first().get(self.units_key)
                query_sum = self.calculate_total(units_value)

        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()

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
            return Decimal(0)

    def add_deltas(self, query_data, query_sum):
        """Calculate and add cost deltas to a result set.

        Args:
            query_data (list) The existing query data from execute_query
            query_sum (list) The sum returned by calculate_totals

        Returns:
            (dict) query data with new with keys "value" and "percent"

        """
        delta_filter = copy.deepcopy(self.query_filter)
        delta_group_by = ['date'] + self._get_group_by()
        previous_query = self._create_previous_query(delta_filter)
        previous_dict = self._create_previous_totals(
            previous_query,
            delta_group_by
        )

        for row in query_data:
            key = tuple((row[key] for key in delta_group_by))
            previous_total = previous_dict.get(key, 0)
            current_total = row.get('total', 0)
            row['delta_value'] = current_total - previous_total
            row['delta_percent'] = self._percent_delta(current_total, previous_total)

        # Calculate the delta on the total aggregate
        current_total_sum = Decimal(query_sum.get('value') or 0)
        prev_total_sum = previous_query.aggregate(value=Sum(self.aggregate_key))
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

    def _create_previous_query(self, delta_filter):
        """Get totals from the time period previous to the current report.

        Args:
            delta_filter (dict): A copy of the report filters
        Returns:
            (dict) A dictionary keyed off the grouped values for the report

        """
        if self.time_scope_value in [-1, -2]:
            date_delta = relativedelta.relativedelta(months=1)
        elif self.time_scope_value == -30:
            date_delta = datetime.timedelta(days=30)
        else:
            date_delta = datetime.timedelta(days=10)

        _start = delta_filter.get('usage_start__gte')
        _end = delta_filter.get('usage_end__lte')

        delta_filter['usage_start__gte'] = _start - date_delta
        delta_filter['usage_end__lte'] = _end - date_delta

        if self.is_sum:
            previous_query = AWSCostEntryLineItemDailySummary.objects.filter(
                **delta_filter
            )
        else:
            previous_query = AWSCostEntryLineItem.objects.filter(**delta_filter)

        return previous_query

    def _create_previous_totals(self, previous_query, query_group_by):
        """Get totals from the time period previous to the current report.

        Args:
            previous_query (Query): A Django ORM query
            query_group_by (dict): The group by dict for the current report
        Returns:
            (dict) A dictionary keyed off the grouped values for the report

        """
        if self.time_scope_value in [-1, -2]:
            date_delta = relativedelta.relativedelta(months=1)
        elif self.time_scope_value == -30:
            date_delta = datetime.timedelta(days=30)
        else:
            date_delta = datetime.timedelta(days=10)
        # Added deltas for each grouping
        # e.g. date, account, region, availability zone, et cetera
        query_annotations = self._get_annotations()
        previous_sums = previous_query.annotate(**query_annotations)
        previous_sums = previous_sums\
            .values(*query_group_by)\
            .annotate(total=Sum(self.aggregate_key))

        previous_dict = OrderedDict()
        for row in previous_sums:
            date = self.string_to_date(row['date'])
            date = date + date_delta
            row['date'] = self.date_to_string(date)
            key = tuple((row[key] for key in query_group_by))
            previous_dict[key] = row['total']

        return previous_dict

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

        for field in filter_fields:
            total_filter.update(
                {key: value for key, value in self.query_filter.items()
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
