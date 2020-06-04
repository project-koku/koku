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
"""Access the current date for masu to use."""
import logging
from datetime import datetime
from datetime import tzinfo

import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta

from masu.config import Config

LOG = logging.getLogger(__name__)


class DateAccessorError(Exception):
    """An exception during date processing."""


class DateAccessor:
    """Accessor to get date time."""

    mock_date_time = None
    date_time_last_accessed = datetime.now(tz=pytz.UTC)

    def __init__(self):
        """Initializer."""
        if Config.MASU_DATE_OVERRIDE and Config.DEBUG and DateAccessor.mock_date_time is None:
            # python-dateutil is needed in Python <=3.6.x;
            # in Python 3.7 there is datetime.fromisoformat()
            DateAccessor.mock_date_time = parser.parse(Config.MASU_DATE_OVERRIDE)
            if DateAccessor.mock_date_time.tzinfo is None:
                DateAccessor.mock_date_time = DateAccessor.mock_date_time.replace(tzinfo=pytz.UTC)
            LOG.info("Initializing masu date/time to %s", str(DateAccessor.mock_date_time))

    def today(self):
        """
        Return the current date and time.

        When the environment variable MASU_DEBUG is set to True,
        the MASU_DATE_OVERRIDE environment variable can be used to
        override masu's current date and time.

        Args:
            (None)

        Returns:
            (datetime.datetime): Current datetime object
            example: 2018-07-24 15:47:33

        """
        current_date = datetime.now(tz=pytz.UTC)
        if Config.DEBUG and DateAccessor.mock_date_time:
            seconds_delta = current_date - DateAccessor.date_time_last_accessed
            DateAccessor.date_time_last_accessed = current_date

            DateAccessor.mock_date_time = DateAccessor.mock_date_time + seconds_delta
            current_date = DateAccessor.mock_date_time
        return current_date

    def today_with_timezone(self, timezone):
        """Return the current datetime at the timezone indictated.

        When the environment variable MASU_DEBUG is set to True,
        the MASU_DATE_OVERRIDE environment variable can be used to
        override masu's current date and time.

        Args:
            timezone (str/datetime.tzinfo) Either a valid timezone string
                or an instance or subclass of datetime.tzinfo.
            examples: 'US/Eastern', pytz.UTC


        Returns:
            (datetime.datetime): Current datetime object
            example: 2018-07-24 15:47:33

        """
        if isinstance(timezone, str):
            try:
                timezone = pytz.timezone(timezone)
            except pytz.exceptions.UnknownTimeZoneError as err:
                LOG.error(err)
                raise DateAccessorError(err)
        elif not isinstance(timezone, tzinfo):
            err = "timezone must be a valid timezone string or subclass of datetime.tzinfo"
            raise DateAccessorError(err)

        current_date = datetime.now(tz=timezone)
        if Config.DEBUG and DateAccessor.mock_date_time:
            seconds_delta = current_date - DateAccessor.date_time_last_accessed
            DateAccessor.date_time_last_accessed = current_date

            DateAccessor.mock_date_time = DateAccessor.mock_date_time + seconds_delta
            current_date = DateAccessor.mock_date_time

        return current_date

    def get_billing_months(self, number_of_months):
        """Return a list of datetimes for the number of months to ingest

        Args:
            number_of_months (int) The the number of months (bills) to ingest.

        Returns:
            (list) of datetime.datetime objects in YYYY-MM-DD format.
            example: ["2020-01-01", "2020-02-01"]
        """
        months = []
        current_month = self.today().replace(day=1, second=1, microsecond=1)
        for month in reversed(range(number_of_months)):
            calculated_month = current_month + relativedelta(months=-month)
            months.append(calculated_month.date())
        return months
