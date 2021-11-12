#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates Azure report summary tables in the database with charge information."""
import logging

from tenant_schemas.utils import schema_context

from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.azure.common import get_bills_from_provider

LOG = logging.getLogger(__name__)


class AzureCostModelCostUpdaterError(Exception):
    """AzureCostModelCostUpdater error."""


class AzureCostModelCostUpdater:
    """Class to update Azure report summary data with charge information."""

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

            with AzureReportDBAccessor(self._schema) as report_accessor:
                with schema_context(self._schema):
                    bill_ids = [str(bill.id) for bill in bills]
                report_accessor.populate_markup_cost(self._provider.uuid, markup_value, start_date, end_date, bill_ids)
        except AzureCostModelCostUpdaterError as error:
            LOG.error("Unable to update markup costs. Error: %s", str(error))

    def update_summary_cost_model_costs(self, start_date=None, end_date=None):
        """Update the Azure summary table with the charge information.

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

        with AzureReportDBAccessor(self._schema) as accessor:
            LOG.debug(
                "Updating Azure derived cost summary for schema: %s and provider: %s",
                self._schema,
                self._provider.uuid,
            )
            bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
            with schema_context(self._schema):
                for bill in bills:
                    bill.derived_cost_datetime = DateAccessor().today_with_timezone("UTC")
                    bill.save()
