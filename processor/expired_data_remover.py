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
"""Remove expired report data."""

import logging
from datetime import (datetime, timedelta)

from masu.config import Config
from masu.database.report_db_cleaner import ReportDBCleaner
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ExpiredDataRemover():
    """
    Removes expired report data based on masu's retention policy.

    Retention policy can be configured via environment variable.

    """

    def __init__(self, customer_schema, num_of_months_to_keep=Config.MASU_RETAIN_NUM_MONTHS):
        """
        Initializer.

        Args:
            customer_schema (String): Schema name for given customer.
            num_of_months_to_keep (Int): Number of months to retain in database.
        """
        self._schema = customer_schema
        self._months_to_keep = num_of_months_to_keep
        self._expiration_date = self._calculate_expiration_date()

    def _calculate_expiration_date(self):
        """
        Calculate the expiration date based on the retention policy.

        Args:
            None

        Returns:
            (datetime.datetime) Expiration date

        """
        today = DateAccessor().today()
        LOG.info('Current date time is %s', today)

        middle_of_current_month = today.replace(day=15)
        num_of_days_to_expire_date = self._months_to_keep * timedelta(days=30)
        middle_of_expire_date_month = middle_of_current_month - num_of_days_to_expire_date
        expiration_date = datetime(year=middle_of_expire_date_month.year,
                                   month=middle_of_expire_date_month.month,
                                   day=1)
        expiration_msg = 'Report data expiration is {} for a {} month retention policy'
        msg = expiration_msg.format(expiration_date, self._months_to_keep)
        LOG.info(msg)
        return expiration_date

    def remove(self, simulate=False):
        """
        Remove expired data based on the retention policy.

        Args:
            None

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        expiration_date = self._calculate_expiration_date()
        cleaner = ReportDBCleaner(self._schema)
        removed_data = cleaner.purge_expired_report_data(expiration_date, simulate)
        return removed_data
