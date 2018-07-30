#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Removes report data from database."""

import logging

from masu.database.report_db_accessor import ReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ReportDBCleaner():
    """Class to remove report data."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        self._accessor = ReportDBAccessor(schema,
                                          ReportingCommonDBAccessor().column_map)

    def purge_expired_report_data(self, expired_date):
        """Remove report data with a billing start period before specified dat.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.

        Returns:
            (None)

        """
        bill_objects = self._accessor.get_bill_query_before_date(expired_date)
        for bill in bill_objects.all():
            bill_id = bill.id

            line_item_query = self._accessor.get_lineitem_query_for_billid(bill_id)
            for line_item in line_item_query.all():
                LOG.debug('Attempting to remove cost item data for bill id: %s, usage_start: %s',
                          bill_id, line_item.usage_start)
                self._accessor.session.delete(line_item)

            cost_entry_query = self._accessor.get_cost_entry_query_for_billid(bill_id)
            for cost_entry in cost_entry_query.all():
                LOG.debug('Attempting to remove cost entry for bill id: %s, interval_start: %s',
                          bill_id, cost_entry.interval_start)
                self._accessor.session.delete(cost_entry)

            self._accessor.session.delete(bill)
            self._accessor.session.commit()
            LOG.info('Report data removed for Account Payer ID: %s with billing period: %s',
                     bill.payer_account_id, bill.billing_period_start)
