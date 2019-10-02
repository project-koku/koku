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
"""Updates AWS report summary tables in the database with charge information."""
import logging

from tenant_schemas.utils import schema_context

from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.aws.common import get_bills_from_provider

LOG = logging.getLogger(__name__)


class AWSReportChargeUpdaterError(Exception):
    """AWSReportChargeUpdater error."""


# pylint: disable=too-few-public-methods
class AWSReportChargeUpdater:
    """Class to update AWS report summary data with charge information."""

    def __init__(self, schema, provider_uuid, provider_id):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._provider_id = provider_id
        self._provider_uuid = provider_uuid
        self._schema = schema
        with ReportingCommonDBAccessor() as reporting_common:
            self._column_map = reporting_common.column_map

    def _update_markup_cost(self, start_date, end_date):
        """Store markup costs."""
        try:
            bills = get_bills_from_provider(
                self._provider_uuid,
                self._schema,
                start_date,
                end_date
            )
            with CostModelDBAccessor(self._schema, self._provider_uuid,
                                     self._column_map) as cost_model_accessor:
                markup = cost_model_accessor.get_markup()
                markup_value = float(markup.get('value', 0)) / 100

            with AWSReportDBAccessor(self._schema, self._column_map) as report_accessor:
                with schema_context(self._schema):
                    bill_ids = [str(bill.id) for bill in bills]
                report_accessor.populate_markup_cost(markup_value, bill_ids)
        except AWSReportChargeUpdaterError as error:
            LOG.error('Unable to update markup costs. Error: %s', str(error))

    def update_summary_charge_info(self, start_date=None, end_date=None):
        """Update the AWS summary table with the charge information.

        Args:
            start_date (str, Optional) - Start date of range to update derived cost.
            end_date (str, Optional) - End date of range to update derived cost.

        Returns
            None

        """
        LOG.debug('Starting charge calculation updates for provider: %s. Dates: %s-%s',
                  self._provider_uuid, str(start_date), str(end_date))

        with AWSReportDBAccessor(self._schema, self._column_map) as accessor:
            LOG.debug('Updating AWS derived cost summary for schema: %s and provider: %s',
                      self._schema, self._provider_uuid)
            bills = accessor.bills_for_provider_id(self._provider_id, start_date)
            with schema_context(self._schema):
                for bill in bills:
                    bill.derived_cost_datetime = DateAccessor().today_with_timezone('UTC')
                    bill.save()
        self._update_markup_cost(start_date, end_date)
