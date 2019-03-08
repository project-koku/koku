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
"""Query Handling for all APIs."""
import datetime
import logging

from dateutil.relativedelta import relativedelta
from django.db.models.functions import TruncDay, TruncMonth

from api.query_filter import QueryFilter, QueryFilterCollection
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


class QueryHandler(object):
    """Handles report queries and responses."""

    def __init__(self, query_parameters, url_data,
                 tenant, default_ordering, **kwargs):
        """Establish query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            default_ordering (String) default ordering of response items
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        LOG.debug(f'Query Params: {query_parameters}')
        self.query_parameters = query_parameters
        self.url_data = url_data
        self.tenant = tenant
        self.default_ordering = default_ordering
        self.kwargs = kwargs
        self.time_interval = []
        self.start_datetime = None
        self.end_datetime = None
        self._max_rank = 0

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

        self._get_timeframe()

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
    def max_rank(self):
        """Return the max rank of a ranked list."""
        return self._max_rank

    @max_rank.setter
    def max_rank(self, max_rank):
        """Max rank setter."""
        self._max_rank = max_rank

    @property
    def resolution(self):
        """Time resolution property.

        Returns:
            (str) 'daily', 'monthly', 'yearly'; default: daily

        """
        return self.get_query_param_data('filter', 'resolution',
                                         default='daily')

    @property
    def time_scope_units(self):
        """Time scope units property.

        Returns:
            (str) 'day', 'month', 'year'; default: day

        """
        return self.get_query_param_data('filter', 'time_scope_units',
                                         default='month')

    @property
    def time_scope_value(self):
        """Time scope value property.

        Returns:
            (int) number of time_scope_units to report on; default: -1

        """
        val = self.get_query_param_data('filter', 'time_scope_value',
                                        default=-1)
        return int(val)

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

    def _get_timeframe(self):
        """Obtain timeframe start and end dates.

        Returns:
            (DateTime): start datetime for query filter
            (DateTime): end datetime for query filter

        """
        dh = DateHelper()
        self.end_datetime = dh.today
        if self.time_scope_units == 'month':
            self.start_datetime = dh.n_months_ago(dh.next_month_start,
                                                  abs(self.time_scope_value))
        else:
            self.start_datetime = dh.n_days_ago(dh.today,
                                                abs(self.time_scope_value))

        self._create_time_interval()
        return (self.start_datetime, self.end_datetime, self.time_interval)

    def _create_time_interval(self):
        """Create list of date times in interval.

        Returns:
            (List[DateTime]): List of all interval slices by resolution

        """
        self.time_interval = sorted(self.gen_time_interval(
            self.start_datetime,
            self.end_datetime))
        return self.time_interval

    def _get_date_delta(self):
        """Return a time delta."""
        if self.time_scope_units == 'month':
            return relativedelta(months=abs(self.time_scope_value))
        else:
            return relativedelta(days=abs(self.time_scope_value))

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = QueryFilterCollection()

        # add time constraint filters
        if delta:
            date_delta = self._get_date_delta()
            start = self.start_datetime - date_delta
            end = self.end_datetime - date_delta
        else:
            start = self.start_datetime
            end = self.end_datetime

        start_filter = QueryFilter(field='usage_start__date', operation='gte',
                                   parameter=start)
        end_filter = QueryFilter(field='usage_end__date', operation='lte',
                                 parameter=end)
        filters.add(query_filter=start_filter)
        filters.add(query_filter=end_filter)

        return filters
