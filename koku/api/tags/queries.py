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
import datetime
import logging
from api.report.query_filter import QueryFilter, QueryFilterCollection  # TODO Move this somewhere generic

from django.db.models.functions import TruncDay, TruncMonth
from api.utils import DateHelper

LOG = logging.getLogger(__name__)
WILDCARD = '*'

class TruncMonthString(TruncMonth):
    """Class to handle string formated day truncation."""

    def convert_value(self, value, expression, connection):
        """Convert value to a string after super."""
        value = super().convert_value(value, expression, connection)
        return value.strftime('%Y-%m')

class TruncDayString(TruncDay):
    """Class to handle string formated day truncation."""

    def convert_value(self, value, expression, connection):
        """Convert value to a string after super."""
        value = super().convert_value(value, expression, connection)
        return value.strftime('%Y-%m-%d')

class TagQueryHandler(object):
    """Handles tag queries and responses."""

    def __init__(self, query_parameters, url_data,
                 tenant, **kwargs):
        LOG.debug(f'Query Params: {query_parameters}')
        self.query_parameters = query_parameters
        self.url_data = url_data  # TODO only used in groupby, maybe don't need this
        self.tenant = tenant
        self.resolution = None
        self.time_scope_units = None
        self.time_scope_value = None
        self.start_datetime = None
        self.end_datetime = None
        # self.query_filter = self._get_filter()
        self._get_timeframe()

    def check_query_params(self, key, in_key):
        """Test if query parameters has a given key and key within it.

        Args:
        key     (String): key to check in query parameters
        in_key  (String): key to check if key is found in query parameters

        Returns:
            (Boolean): True if they keys given appear in given query parameters.

        """
        return (self.query_parameters and key in self.query_parameters and  # noqa: W504
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
                start = dh.n_days_ago(dh.this_hour, 9)
                end = dh.this_hour
            else:
                # get last 30 days
                start = dh.n_days_ago(dh.this_hour, 29)
                end = dh.this_hour

        self.start_datetime = start
        self.end_datetime = end
        self._create_time_interval()
        return (self.start_datetime, self.end_datetime, self.time_interval)
