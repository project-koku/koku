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

from django.db.models import Count, Sum, Value
from django.db.models.functions import Concat, TruncDay, TruncMonth
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

    def get_filter_data(self, key):
        """Extract the value from filter parameter or return None.

        Args:
            key     (String): the key to obtain from the filter data
        Returns:
            (Object): The value found with the given key or None
        """
        value = None
        if self.check_query_params('filter', key):
            value = self.query_parameters.get('filter').get(key)
        return value

    def get_group_by_data(self, key):
        """Extract the value from group_by parameter or return None.

        Args:
            key     (String): the key to obtain from the group_by data
        Returns:
            (Object): The value found with the given key or None
        """
        value = None
        if self.check_query_params('group_by', key):
            value = self.query_parameters.get('group_by').get(key)
        return value

    def get_resolution(self):
        """Extract resolution or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        if self.resolution:
            return self.resolution

        self.resolution = self.get_filter_data('resolution')
        time_scope_value = self.get_filter_data('time_scope_value')
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

        time_scope_units = self.get_filter_data('time_scope_units')
        time_scope_value = self.get_filter_data('time_scope_value')
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

        time_scope_units = self.get_filter_data('time_scope_units')
        time_scope_value = self.get_filter_data('time_scope_value')
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

        service = self.get_group_by_data('service')
        account = self.get_group_by_data('account')
        if not ReportQueryHandler.has_wildcard(service) and service:
            filter_dict['cost_entry_product__product_family__in'] = service

        if not ReportQueryHandler.has_wildcard(account) and account:
            filter_dict['usage_account_id__in'] = account

        return filter_dict

    def _get_group_by(self):
        """Create list for group_by parameters."""
        group_by = []
        group_by_options = ['service', 'account']
        for item in group_by_options:
            group_data = self.get_group_by_data(item)
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
        service = self.get_group_by_data('service')
        account = self.get_group_by_data('account')
        if service:
            annotations['service'] = Concat(
                'cost_entry_product__product_family', Value(''))
        if account:
            annotations['account'] = Concat(
                'usage_account_id', Value(''))

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
            group_by = self._get_group_by()
            grouped = ReportQueryHandler._group_data_by_list(group_by, 0,
                                                             data_list)
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
        query_sum = None
        data = []

        with tenant_context(self.tenant):
            query_filter = self._get_filter()
            query_group_by = self._get_group_by()
            query_annotations = self._get_annotations()
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

            query_data = query_data.order_by('-date', '-total')
            data = self._apply_group_by(list(query_data))
            data = self._transform_data(query_group_by, 0, data)

            if query.exists():
                units_value = query.values(self.units_key).first().get(self.units_key)
                query_sum = query.aggregate(value=Sum(self.aggregate_key))
                query_sum['units'] = units_value
                if self._count:
                    query_sum.update(
                        query.aggregate(
                            count=Count(self._count, distinct=True)
                        )
                    )

        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()
