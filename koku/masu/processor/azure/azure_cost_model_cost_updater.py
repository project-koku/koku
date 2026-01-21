#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates Azure report summary tables in the database with charge information."""
import logging
from decimal import Decimal

from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.util.azure.common import get_bills_from_provider
from masu.util.common import SummaryRangeConfig


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
        self._context = {
            "schema": self._schema,
            "provider_uuid": self._provider.uuid,
        }

    def _update_markup_cost(self, start_date, end_date):
        """Store markup costs."""
        try:
            bills = get_bills_from_provider(self._provider.uuid, self._schema, start_date, end_date)
            with CostModelDBAccessor(self._schema, self._provider.uuid) as cost_model_accessor:
                markup = cost_model_accessor.markup
                markup_value = Decimal(markup.get("value", 0)) / 100

            with AzureReportDBAccessor(self._schema) as report_accessor:
                with schema_context(self._schema):
                    bill_ids = [str(bill.id) for bill in bills]
                report_accessor.populate_markup_cost(self._provider.uuid, markup_value, start_date, end_date, bill_ids)
        except AzureCostModelCostUpdaterError as error:
            LOG.error(log_json(msg="unable to update markup costs", context=self._context), exc_info=error)

    def update_summary_cost_model_costs(self, summary_range: SummaryRangeConfig) -> None:
        """Update the Azure summary table with the charge information.

        Args:
            summary_range (SummaryRangeConfig) - Date range configuration for cost model updates.

        Returns
            None

        """
        LOG.debug(
            log_json(
                msg="starting charge calculation updates",
                context=self._context,
                start_date=summary_range.start_date,
                end_date=summary_range.end_date,
            )
        )

        self._update_markup_cost(summary_range.start_date, summary_range.end_date)

        with AzureReportDBAccessor(self._schema) as accessor:
            LOG.debug(log_json(msg="updating Azure derived cost summary", context=self._context))
            accessor.populate_ui_summary_tables(summary_range.start_date, summary_range.end_date, self._provider.uuid)
            bills = accessor.bills_for_provider_uuid(self._provider.uuid, summary_range.start_date)
            with schema_context(self._schema):
                for bill in bills:
                    bill.derived_cost_datetime = timezone.now()
                    bill.save()
