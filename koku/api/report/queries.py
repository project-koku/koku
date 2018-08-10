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
from itertools import groupby

from django.db.models import (Count,
                              F,
                              Sum,
                              Value,
                              Window)
from django.db.models.functions import (Concat,
                                        DenseRank,
                                        TruncDay,
                                        TruncMonth)
from django.utils import timezone
from tenant_schemas.utils import tenant_context

from reporting.models import AWSCostEntryLineItem


WILDCARD = '*'


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
        self.query_parameters = query_parameters
        self.url_data = url_data
        self.tenant = tenant
        self.aggregate_key = aggregate_key
        self.units_key = units_key
        self._filter = None
        self._group_by = None
        self._annotations = None
        self._count = None
        self._limit = self.get_query_param_data('filter', 'limit')
        self._order = self.get_order()
        self.resolution = None
        self.time_scope_value = None
        self.time_scope_units = None
        self.start_datetime = None
        self.end_datetime = None
        self.time_interval = []
        self._get_timeframe()

        if kwargs:
            if 'filter' in kwargs:
                self._filter = kwargs.get('filter')
            if 'group_by' in kwargs:
                self._group_by = kwargs.get('group_by')
            if 'annotations' in kwargs:
                self._annotations = kwargs.get('annotations')
            if 'count' in kwargs:
                self._count = kwargs.get('count')

    @staticmethod
    def next_month(in_date):
        """Return the first of the next month from the in_date.

        Args:
            in_date    (DateTime) input datetime
        Returns:
            (DateTime): First of the next month
        """
        dt_next_month = in_date.replace(month=(in_date.month + 1), day=1)
        return dt_next_month

    @staticmethod
    def previous_month(in_date):
        """Return the first of the previous month from the in_date.

        Args:
            in_date    (DateTime) input datetime
        Returns:
            (DateTime): First of the previous month
        """
        dt_prev_month = in_date.replace(month=(in_date.month - 1), day=1)
        return dt_prev_month

    @staticmethod
    def n_days_ago(in_date, n_days):
        """Return midnight of the n days from the in_date in past.

        Args:
            in_date    (DateTime) input datetime
            n_days     (integer) number of days in the past
        Returns:
            (DateTime): A day n days in the past
        """
        dt_midnight = in_date.replace(hour=0)
        dt_n_days = dt_midnight - datetime.timedelta(days=n_days)
        return dt_n_days

    @staticmethod
    def list_days(start_date, end_date):
        """Return a list of days from the start date til the end date.

        Args:
            start_date    (DateTime) starting datetime
            end_date      (DateTime) ending datetime
        Returns:
            (List[DateTime]): A list of days from the start date to end date
        """
        day_list = []
        end_midnight = end_date.replace(hour=0)
        start_midnight = start_date.replace(hour=0)
        days = (end_midnight - start_midnight).days + 1
        day_list = [start_midnight + datetime.timedelta(i) for i in range(days)]
        return day_list

    @staticmethod
    def list_months(start_date, end_date):
        """Return a list of months from the start date til the end date.

        Args:
            start_date    (DateTime) starting datetime
            end_date      (DateTime) ending datetime
        Returns:
            (List[DateTime]): A list of months from the start date to end date
        """
        months = []
        dt_first = start_date.replace(hour=0, day=1)
        end_midnight = end_date.replace(hour=0)
        current = dt_first
        while current < end_midnight:
            months.append(current)
            next_month = ReportQueryHandler.next_month(current)
            current = next_month
        return months

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

    def get_query_param_data(self, dictkey, key):
        """Extract the value from a query parameter dictionary or return None.

        Args:
            dictkey (String): the key to access a query parameter dictionary
            key     (String): the key to obtain from the dictionar data
        Returns:
            (Object): The value found with the given key or None
        """
        value = []
        if self.check_query_params(dictkey, key):
            value = self.query_parameters.get(dictkey).get(key)
        return value

    def get_order(self):
        """Extract the order parameters and apply the associated ordering.

        Returns:
            (String): Ordering value either `total` or `-total`; default is -total

        """
        order = '-total'
        cost = self.get_query_param_data('order_by', 'cost')
        if cost and cost == 'asc':
            order = 'total'
        return order

    def get_resolution(self):
        """Extract resolution or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        if self.resolution:
            return self.resolution

        self.resolution = self.get_query_param_data('filter', 'resolution')
        time_scope_value = self.get_query_param_data('filter', 'time_scope_value')
        if not self.resolution:
            if not time_scope_value:
                self.resolution = 'daily'
            elif int(time_scope_value) == -1 or int(time_scope_value) == -2:
                self.resolution = 'monthly'
            else:
                self.resolution = 'daily'
        if self.resolution == 'monthly':
            self.date_to_string = lambda datetime: datetime.strftime('%Y-%m')
            self.date_trunc = TruncMonthString
            self.gen_time_interval = ReportQueryHandler.list_months
        else:
            self.date_to_string = lambda datetime: datetime.strftime('%Y-%m-%d')
            self.date_trunc = TruncDayString
            self.gen_time_interval = ReportQueryHandler.list_days

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
            if not time_scope_value:
                time_scope_units = 'day'
            elif int(time_scope_value) == -1 or int(time_scope_value) == -2:
                time_scope_units = 'month'
            else:
                time_scope_units = 'day'
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
            if not time_scope_units:
                time_scope_value = -10
            elif time_scope_units == 'month':
                time_scope_value = -1
            else:
                time_scope_value = -10
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
        this_hour = timezone.now().replace(microsecond=0, second=0, minute=0)
        start = None
        end = None
        if time_scope_units == 'month':
            if time_scope_value == -1:
                # get current month
                start = this_hour.replace(microsecond=0, second=0, minute=0, hour=0, day=1)
                end = ReportQueryHandler.next_month(start)
            else:
                # get previous month
                end = this_hour.replace(microsecond=0, second=0, minute=0, hour=0, day=1)
                start = ReportQueryHandler.previous_month(end)
        else:
            if time_scope_value == -10:
                # get last 10 days
                end = this_hour
                start = ReportQueryHandler.n_days_ago(this_hour, 10)
            else:
                # get last 30 days
                end = this_hour
                start = ReportQueryHandler.n_days_ago(this_hour, 30)
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
        if self._filter:
            filter_dict.update(self._filter)

        gb_service = self.get_query_param_data('group_by', 'service')
        gb_account = self.get_query_param_data('group_by', 'account')
        gb_region = self.get_query_param_data('group_by', 'region')
        gb_avail_zone = self.get_query_param_data('group_by', 'avail_zone')
        f_account = self.get_query_param_data('filter', 'account')
        f_service = self.get_query_param_data('filter', 'service')
        f_region = self.get_query_param_data('filter', 'region')
        f_avail_zone = self.get_query_param_data('filter', 'avail_zone')
        account = list(set(gb_account + f_account))
        service = list(set(gb_service + f_service))
        region = list(set(gb_region + f_region))
        avail_zone = list(set(gb_avail_zone + f_avail_zone))

        if not ReportQueryHandler.has_wildcard(service) and service:
            filter_dict['product_code__in'] = service

        if not ReportQueryHandler.has_wildcard(account) and account:
            filter_dict['usage_account_id__in'] = account

        if not ReportQueryHandler.has_wildcard(region) and region:
            filter_dict['cost_entry_product__region__in'] = region

        if not ReportQueryHandler.has_wildcard(avail_zone) and avail_zone:
            filter_dict['availability_zone__in'] = avail_zone

        return filter_dict

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

    def _get_annotations(self):
        """Create dictionary for query annotations.

        Returns:
            (Dict): query annotations dictionary

        """
        annotations = {
            'date': self.date_trunc('usage_start'),
            'units': Concat(self.units_key, Value(''))
        }
        if self._annotations:
            annotations.update(self._annotations)
        service = self.get_query_param_data('group_by', 'service')
        account = self.get_query_param_data('group_by', 'account')
        region = self.get_query_param_data('group_by', 'region')
        avail_zone = self.get_query_param_data('group_by', 'avail_zone')
        if service:
            annotations['service'] = Concat(
                'product_code', Value(''))
        if account:
            annotations['account'] = Concat(
                'usage_account_id', Value(''))
        if region:
            annotations['region'] = Concat(
                'cost_entry_product__region', Value(''))
        if avail_zone:
            annotations['avail_zone'] = Concat(
                'availability_zone', Value(''))

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

        out_data = {}
        curr_group = group_by_list[group_index]

        for key, group in groupby(data, lambda by: by.get(curr_group)):
            grouped = list(group)
            grouped = ReportQueryHandler._group_data_by_list(group_by_list,
                                                             (group_index + 1),
                                                             grouped)
            if out_data.get(key):
                out_data[key].update(grouped)
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
        bucket_by_date = {}
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

    def execute_query(self):
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
            query_order_by = ('-date', self._order)
            query = AWSCostEntryLineItem.objects.filter(**query_filter)
            query_data = query.annotate(**query_annotations)
            query_group_by = ['date'] + query_group_by
            query_group_by_with_units = query_group_by + ['units']
            query_data = query_data.values(*query_group_by_with_units)\
                .annotate(total=Sum(self.aggregate_key))

            if self._count:
                query_data = query_data.annotate(
                    count=Count(self._count, distinct=True)
                )

            if self._limit:
                rank_order = F('total').desc()
                if self._order != '-total':
                    rank_order = F('total').asc()
                dense_rank_by_total = Window(
                    expression=DenseRank(),
                    partition_by=F('date'),
                    order_by=rank_order
                )
                query_data = query_data.annotate(rank=dense_rank_by_total)
                query_order_by = query_order_by + ('rank',)

            query_data = query_data.order_by(*query_order_by)
            data = self._apply_group_by(list(query_data))
            data = self._transform_data(query_group_by, 0, data)

            if query.exists():
                units_value = query.values(self.units_key).first().get(self.units_key)
                if self._count:
                    query_sum = query.aggregate(
                        value=Sum(self.aggregate_key),
                        count=Count(self._count, distinct=True)
                    )
                else:
                    query_sum = query.aggregate(value=Sum(self.aggregate_key))
                query_sum['units'] = units_value

        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()
