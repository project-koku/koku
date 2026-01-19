#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates GCP report summary tables in the database with charge information."""
import logging
from decimal import Decimal

from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.util.common import SummaryRangeConfig
from masu.util.gcp.common import get_bills_from_provider
from reporting.provider.gcp.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class GCPCostModelCostUpdaterError(Exception):
    """GCPCostModelCostUpdater error."""


class GCPCostModelCostUpdater:
    """Class to update GCP report summary data with charge information."""

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
                markup_value = Decimal(markup.get("value", 0)) / 100

            with GCPReportDBAccessor(self._schema) as report_accessor:
                with schema_context(self._schema):
                    bill_ids = [str(bill.id) for bill in bills]
                report_accessor.populate_markup_cost(markup_value, start_date, end_date, bill_ids)
        except GCPCostModelCostUpdaterError as error:
            LOG.error(log_json(msg="unable to update markup costs"), exc_info=error)

    def update_summary_cost_model_costs(self, summary_range: SummaryRangeConfig) -> None:
        """Update the GCP summary table with the charge information.

        Args:
            summary_range (SummaryRangeConfig) - Date range configuration for cost model updates.

        Returns
            None

        """
        LOG.debug(
            log_json(
                msg="starting charge calculation updates",
                schema=self._schema,
                provider_uuid=self._provider.uuid,
                start_date=summary_range.start_date,
                end_date=summary_range.end_date,
            )
        )

        self._update_markup_cost(summary_range.start_date, summary_range.end_date)

        with GCPReportDBAccessor(self._schema) as accessor:
            LOG.debug(
                log_json(
                    msg="updating GCP derived cost summary",
                    schema=self._schema,
                    provider_uuid=self._provider.uuid,
                )
            )
            invoice_month = summary_range.start_date.strftime("%Y%m")
            invoice_dates = accessor.fetch_invoice_month_dates(
                summary_range.start_date, summary_range.end_date, invoice_month, self._provider.uuid
            )
            invoice_start, invoice_end = invoice_dates[0]
            accessor.populate_ui_summary_tables(
                invoice_start, invoice_end, self._provider.uuid, invoice_month, UI_SUMMARY_TABLES
            )
            bills = accessor.bills_for_provider_uuid(self._provider.uuid, invoice_month=invoice_month)
            with schema_context(self._schema):
                for bill in bills:
                    bill.derived_cost_datetime = timezone.now()
                    bill.save()
