#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates GCP report summary tables in the database with charge information."""
import logging
from decimal import Decimal

from django_tenants.utils import schema_context

from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.gcp.common import get_bills_from_provider
from reporting.provider.gcp.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class GCPCostModelCostUpdaterError(Exception):
    """GCPCostModelCostUpdater error."""


class GCPCostModelCostUpdater:
    """Class to update GCP report summary data with charge information."""

    def __init__(self, schema_name, provider):
        """Establish the database connection.

        Args:
            schema_name (str): The customer schema to associate with

        """
        self._provider = provider
        self._schema_name = schema_name

    def _update_markup_cost(self, start_date, end_date):
        """Store markup costs."""
        try:
            bills = get_bills_from_provider(self._provider.uuid, self._schema_name, start_date, end_date)
            with CostModelDBAccessor(self._schema_name, self._provider.uuid) as cost_model_accessor:
                markup = cost_model_accessor.markup
                markup_value = Decimal(markup.get("value", 0)) / 100

            with GCPReportDBAccessor(self._schema_name) as report_accessor:
                with schema_context(self._schema_name):
                    bill_ids = [str(bill.id) for bill in bills]
                report_accessor.populate_markup_cost(markup_value, start_date, end_date, bill_ids)
        except GCPCostModelCostUpdaterError as error:
            LOG.error("Unable to update markup costs. Error: %s", str(error))

    def update_summary_cost_model_costs(self, start_date=None, end_date=None):
        """Update the GCP summary table with the charge information.

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

        with GCPReportDBAccessor(self._schema_name) as accessor:
            LOG.debug(
                "Updating GCP derived cost summary for schema_name: %s and provider: %s",
                self._schema_name,
                self._provider.uuid,
            )
            accessor.populate_ui_summary_tables(start_date, end_date, self._provider.uuid, UI_SUMMARY_TABLES)
            bills = accessor.bills_for_provider_uuid(self._provider.uuid, start_date)
            with schema_context(self._schema_name):
                for bill in bills:
                    bill.derived_cost_datetime = DateAccessor().today_with_timezone("UTC")
                    bill.save()
