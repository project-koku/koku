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

from masu.config import Config


LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
# pylint: disable=no-self-use
class DateAccessor():
    """Accessor to get date time."""

    mock_date_time = None
    date_time_last_accessed = datetime.now()

    def __init__(self):
        """Initializer."""
        if Config.MASU_DATE_OVERRIDE and DateAccessor.mock_date_time is None:
            DateAccessor.mock_date_time = datetime.strptime(Config.MASU_DATE_OVERRIDE,
                                                            '%Y-%m-%d %H:%M:%S')
            LOG.info('Initializing masu date/time to %s', str(DateAccessor.mock_date_time))

    def today(self):
        """
        Return the current date and time.

        When the environment varaible MASU_DEBUG is set to True,
        the MASU_DATE_OVERRIDE environment variable can be used to
        override masu's current date and time.

        Args:
            (None)

        Returns:
            (datetime.datetime): Current datetime object
            example: 2018-07-24 15:47:33

        """
        current_date = datetime.today()
        if Config.DEBUG and DateAccessor.mock_date_time:
            seconds_delta = (current_date - DateAccessor.date_time_last_accessed)
            DateAccessor.date_time_last_accessed = current_date

            DateAccessor.mock_date_time = DateAccessor.mock_date_time + seconds_delta
            current_date = DateAccessor.mock_date_time

        return current_date
