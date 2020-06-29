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
from masu.external.date_accessor import DateAccessor
from masu.util.aws.common import get_bills_from_provider

LOG = logging.getLogger(__name__)


class AWSCostModelCostUpdaterError(Exception):
    """AWSCostModelCostUpdater error."""


class AWSCostModelCostUpdater:
    """Class to update AWS report summary data with charge information."""

    def __init__(self, schema, provider):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._provider = provider
        self._schema = schema

    def _update_markup_cost(self, start_date, end_date):
        """Store markup costs."""
        try:
            bills = get_bills_from_provider(self._provider.uuid, self._schema, start_date, end_date)
            with CostModelDBAccessor(self._schema, self._provider.uuid) as cost_model_accessor:
                markup = cost_model_accessor.markup
                markup_value = float(markup.get("value", 0)) / 100

            with AWSReportDBAccessor(self._schema) as report_accessor:
                with schema_context(self._schema):
                    bill_ids = [str(bill.id) for bill in bills]
                report_accessor.populate_markup_cost(markup_value, bill_ids)
        except AWSCostModelCostUpdaterError as error:
            LOG.error("Unable to update markup costs. Error: %s", str(error))

    def update_summary_cost_model_costs(self, start_date=None, end_date=None):
        """Update the AWS summary table with the charge information.

        Args:
            start_date (str, Optional) - Start date of range to update derived cost.
            end_date (str, Optional) - End date of range to update derived cost.

        Returns
            None

        """
        LOG.debug(
            "Starting charge calculation updates for provider: %s. Dates: %s-%s",
            self._provider.uuid,
            str(start_date),
            str(end_date),
        )

        self._update_markup_cost(start_date, end_date)

        with AWSReportDBAccessor(self._schema) as accessor:
            LOG.debug(
                "Updating AWS derived cost summary for schema: %s and provider: %s", self._schema, self._provider.uuid
            )
            bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
            with schema_context(self._schema):
                for bill in bills:
                    bill.derived_cost_datetime = DateAccessor().today_with_timezone("UTC")
                    bill.save()
