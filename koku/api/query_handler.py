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
import copy
import datetime
import logging

from dateutil import relativedelta
from django.db.models.functions import TruncDay, TruncMonth

from api.query_filter import QueryFilter, QueryFilterCollection
from api.utils import DateHelper

LOG = logging.getLogger(__name__)
WILDCARD = '*'


# pylint: disable=abstract-method, too-many-ancestors
class TruncMonthString(TruncMonth):
    """Class to handle string formated day truncation."""

    def convert_value(self, value, expression, connection):
        """Convert value to a string after super."""
        value = super().convert_value(value, expression, connection)
        return value.strftime('%Y-%m')


# pylint: disable=abstract-method, too-many-ancestors
class TruncDayString(TruncDay):
    """Class to handle string formated day truncation."""

    def convert_value(self, value, expression, connection):
        """Convert value to a string after super."""
        value = super().convert_value(value, expression, connection)
        return value.strftime('%Y-%m-%d')


class QueryHandler:
    """Handles report queries and responses."""

    def __init__(self, parameters):
        """Establish query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        LOG.debug(f'Query Params: {parameters}')

        self.tenant = parameters.tenant
        self.access = parameters.access

        self.default_ordering = self._mapper._report_type_map.get('default_ordering')

        self.parameters = parameters
        self.resolution = None
        self.time_interval = []
        self.time_scope_units = None
        self.time_scope_value = None
        self.start_datetime = None
        self.end_datetime = None
        self._max_rank = 0

        self._get_timeframe()

    # FIXME: move this to a standalone utility function.
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
        order_by = self.parameters.get('order_by', self.default_ordering)
        return list(order_by.keys()).pop()

    @property
    def order_direction(self):
        """Order-by orientation value.

        Returns:
            (str) 'asc' or 'desc'; default is 'desc'

        """
        order_by = self.parameters.get('order_by', self.default_ordering)
        return list(order_by.values()).pop()

    @property
    def max_rank(self):
        """Return the max rank of a ranked list."""
        return self._max_rank

    @max_rank.setter
    def max_rank(self, max_rank):
        """Max rank setter."""
        self._max_rank = max_rank

    def get_resolution(self):
        """Extract resolution or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        if self.resolution:
            return self.resolution

        self.resolution = self.parameters.get_filter('resolution',
                                                     default='daily')

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

    def check_query_params(self, key, in_key):
        """Test if query parameters has a given key and key within it.

        Args:
        key     (String): key to check in query parameters
        in_key  (String): key to check if key is found in query parameters

        Returns:
            (Boolean): True if they keys given appear in given query parameters.

        """
        return (self.parameters and key in self.parameters and  # noqa: W504
                in_key in self.parameters.get(key))

    def get_time_scope_units(self):
        """Extract time scope units or provide default.

        Returns:
            (String): The value of how data will be sliced.

        """
        if self.time_scope_units:
            return self.time_scope_units

        time_scope_units = self.parameters.get_filter('time_scope_units',
                                                      default='day')
        self.time_scope_units = time_scope_units
        return self.time_scope_units

    def get_time_scope_value(self):
        """Extract time scope value or provide default.

        Returns:
            (Integer): time relative value providing query scope

        """
        if self.time_scope_value:
            return self.time_scope_value

        time_scope_value = self.parameters.get_filter('time_scope_value',
                                                      default=-10)
        self.time_scope_value = int(time_scope_value)
        return self.time_scope_value

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
                end = dh.today
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
        if self.time_scope_value in [-1, -2]:
            date_delta = relativedelta.relativedelta(months=1)
        elif self.time_scope_value == -30:
            date_delta = datetime.timedelta(days=30)
        else:
            date_delta = datetime.timedelta(days=10)
        return date_delta

    def _get_time_based_filters(self, delta=False):
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
        return start_filter, end_filter

    def _get_filter(self, delta=False):
        """Create dictionary for filter parameters.

        Args:
            delta (Boolean): Construct timeframe for delta
        Returns:
            (Dict): query filter dictionary

        """
        filters = QueryFilterCollection()

        # add time constraint filters
        start_filter, end_filter = self._get_time_based_filters(delta)
        filters.add(query_filter=start_filter)
        filters.add(query_filter=end_filter)

        return filters

    def _get_cluster_group_by(self, group_by):
        """Determine if a GROUP BY list requires implicit group by cluster.

        Args:
            group_by (list): The list of group by params

        Returns:
            (list): A new group by list with cluster if needed

        """
        # To avoid namespace/node name collisions we implicitly
        # group by cluster as well. We make a copy of the group_by
        # here to do the actual grouping, but kepe the original
        # unaltered so as to keep the final API result grouped by
        # the specified group by value
        if 'cluster' in group_by:
            return group_by
        clustered_group_by = copy.copy(group_by)

        for value in group_by:
            if value in ('project', 'node'):
                clustered_group_by.extend(['cluster', 'cluster_alias'])
                break

        for value in self.parameters.get('filter', {}).keys():
            if value in ('project', 'node') and 'cluster_id' not in clustered_group_by:
                clustered_group_by.extend(['cluster', 'cluster_alias'])
                break

        return clustered_group_by
