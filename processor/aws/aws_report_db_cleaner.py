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
class AWSReportDBCleaner():
    """Class to remove report data."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        self._accessor = ReportDBAccessor(schema,
                                          ReportingCommonDBAccessor().column_map)

    def purge_expired_report_data(self, expired_date, simulate=False):
        """Remove report data with a billing start period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        removed_items = []
        bill_objects = self._accessor.get_bill_query_before_date(expired_date)
        for bill in bill_objects.all():
            bill_id = bill.id
            removed_payer_account_id = bill.payer_account_id
            removed_billing_period_start = bill.billing_period_start

            if simulate is False:
                del_count = self._accessor.get_lineitem_query_for_billid(bill_id).delete()
                LOG.info('Removing %s cost entry line items for bill id %s', del_count, bill_id)

                del_count = self._accessor.get_cost_entry_query_for_billid(bill_id).delete()
                LOG.info('Removing %s cost entry items for bill id %s', del_count, bill_id)

            LOG.info('Report data removed for Account Payer ID: %s with billing period: %s',
                     removed_payer_account_id, removed_billing_period_start)
            removed_items.append({'account_payer_id': removed_payer_account_id,
                                  'billing_period_start': str(removed_billing_period_start)})

        if simulate is False:
            bill_objects.delete()
            self._accessor.commit()
        return removed_items
