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

from django.db.models import Sum
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone
from tenant_schemas.utils import tenant_context

from reporting.models import AWSCostEntryLineItem


class ReportQueryHandler(object):
    """Handles report queries and responses."""

    def __init__(self, query_parameters, tenant):
        """Establish report query handler.

        Args:
            query_parameters    (dictionary) parameters for query
            tenant    (String) the tenant to use to access CUR data
        """
        self.query_parameters = query_parameters
        self.tenant = tenant
        self.resolution = None
        self.time_scope_value = None
        self.time_scope_units = None

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
        days = (end_midnight - start_midnight).days
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

    def has_filter(self):
        """Test if query parameters has a filter.

        Returns:
            (Boolean): True if filter appears in given query parameters.

        """
        return self.query_parameters and 'filter' in self.query_parameters

    def get_filter_data(self, key):
        """Extract the value from filter parameter or return None.

        Args:
            key     (String): the key to obtain from the filter data
        Returns:
            (Object): The value found with the given key or None
        """
        value = None
        if self.has_filter() and key in self.query_parameters.get('filter'):
            value = self.query_parameters.get('filter').get(key)
        return value

    def get_resolution(self):
        """Extract resolution or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        if self.resolution:
            return self.resolution

        resolution = self.get_filter_data('resolution')
        time_scope_value = self.get_filter_data('time_scope_value')
        if not resolution:
            if not time_scope_value:
                resolution = 'daily'
            elif int(time_scope_value) == -1 or int(time_scope_value) == -2:
                resolution = 'monthly'
            else:
                resolution = 'daily'
        self.resolution = resolution
        return resolution

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
        return time_scope_units

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
        return time_scope_value

    def _get_time_frame_filter(self):
        """Obtain time frame filter.

        Returns:
            (DateTime): start datetime for query filter
            (DateTime): end datetime for query filter
            (List[DateTime]): List of all interval slices by resolution

        """
        time_scope_value = self.get_time_scope_value()
        time_scope_units = self.get_time_scope_units()
        resolution = self.get_resolution()
        this_hour = timezone.now().replace(microsecond=0, second=0, minute=0)
        start = None
        end = None
        interval = []
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

        if start and end and resolution == 'daily':
            interval = ReportQueryHandler.list_days(start, end)
        if start and end and resolution == 'monthly':
            interval = ReportQueryHandler.list_months(start, end)
        interval = sorted(interval)
        return (start, end, interval)

    def _add_interval_data(self, interval, query_data):
        """Add the interval data if not present in cost usage data.

        Args:
            interval    (List[DateTime]): Valid interval list sliced by resolution
            query_data  (List(Dict)): Queried data
        Returns:
            (List[Dict]): List of data for all intervals sliced by resolution

        """
        current = {}
        data = []
        resolution = self.get_resolution()
        if query_data:
            current = query_data.pop()
        for item in interval:
            interval_item = item.date()
            if resolution == 'daily':
                interval_str = interval_item.strftime('%Y-%m-%d')
            else:
                interval_str = interval_item.strftime('%Y-%m')
            cur_date = None
            if current.get('date'):
                cur_date = current.get('date').date()
            if cur_date == interval_item:
                data.append({'date': interval_str,
                             'total_cost': current.get('total_cost'),
                             'units': 'USD'})
                if query_data:
                    current = query_data.pop()
            else:
                data.append({'date': interval_str,
                             'total_cost': None,
                             'units': None})
        return data

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = copy.deepcopy(self.query_parameters)
        output['data'] = self.query_data
        output['total'] = self.query_sum
        return output

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = None
        data = []
        if self.get_resolution() == 'daily':
            trunc_func = TruncDay
        else:
            trunc_func = TruncMonth

        with tenant_context(self.tenant):
            start, end, interval = self._get_time_frame_filter()
            time_frame_query = AWSCostEntryLineItem.objects.filter(
                usage_start__gte=start,
                usage_end__lte=end)
            query_sum = time_frame_query.aggregate(value=Sum('unblended_cost'))
            query_sum['units'] = 'USD'
            query_data = list(time_frame_query.annotate(date=trunc_func('usage_start')).values(
                'date').annotate(total_cost=Sum('unblended_cost')).order_by('-date', 'total_cost'))
            data = self._add_interval_data(interval, query_data)
        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()
