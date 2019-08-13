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

from tenant_schemas.utils import schema_context

from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor

LOG = logging.getLogger(__name__)


class AWSReportDBCleanerError(Exception):
    """Raise an error during AWS report cleaning."""


# pylint: disable=too-few-public-methods
class AWSReportDBCleaner():
    """Class to remove report data."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema

    # pylint: disable=too-many-locals
    def purge_expired_report_data(self, expired_date=None, provider_id=None, simulate=False):
        """Remove report data with a billing start period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_id (str): The DB id of the provider to purge data for.
            simulate (bool): Whether to simluate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'account_payer_id' and 'billing_period_start'

        """
        with ReportingCommonDBAccessor() as reporting_common:
            column_map = reporting_common.column_map

        with AWSReportDBAccessor(self._schema, column_map) as accessor:
            if ((expired_date is None and provider_id is None) or  # noqa: W504
                    (expired_date is not None and provider_id is not None)):
                err = 'This method must be called with either expired_date or provider_id'
                raise AWSReportDBCleanerError(err)
            removed_items = []

            if expired_date is not None:
                bill_objects = accessor.get_bill_query_before_date(expired_date)
            else:
                bill_objects = accessor.get_cost_entry_bills_query_by_provider(provider_id)
            with schema_context(self._schema):
                for bill in bill_objects.all():
                    bill_id = bill.id
                    removed_payer_account_id = bill.payer_account_id
                    removed_billing_period_start = bill.billing_period_start

                    if not simulate:
                        del_count = accessor.get_ocp_aws_summary_query_for_billid(bill_id).delete()
                        LOG.info('Removing %s OCP-on-AWS summary items for bill id %s',
                                 del_count, bill_id)

                        del_count = accessor.get_ocp_aws_project_summary_query_for_billid(bill_id).\
                            delete()
                        LOG.info('Removing %s OCP-on-AWS project summary items for bill id %s',
                                 del_count, bill_id)

                        del_count = accessor.get_lineitem_query_for_billid(bill_id).delete()
                        LOG.info('Removing %s cost entry line items for bill id %s',
                                 del_count, bill_id)

                        del_count = accessor.get_daily_query_for_billid(bill_id).delete()
                        LOG.info('Removing %s cost entry daily items for bill id %s',
                                 del_count, bill_id)

                        del_count = accessor.get_summary_query_for_billid(bill_id).delete()
                        LOG.info('Removing %s cost entry summary items for bill id %s',
                                 del_count, bill_id)

                        del_count = accessor.get_cost_entry_query_for_billid(bill_id).delete()
                        LOG.info('Removing %s cost entry items for bill id %s',
                                 del_count, bill_id)

                    LOG.info('Report data removed for Account Payer ID: %s with billing period: %s',
                             removed_payer_account_id, removed_billing_period_start)
                    removed_items.append({'account_payer_id': removed_payer_account_id,
                                          'billing_period_start':
                                              str(removed_billing_period_start)})

                if not simulate:
                    bill_objects.delete()

        return removed_items
