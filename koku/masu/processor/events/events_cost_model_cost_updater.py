#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates Events report summary tables with CostModel markup/discount costs."""
import logging
from decimal import Decimal

from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.events_report_db_accessor import EventsReportDBAccessor
from masu.util.common import SummaryRangeConfig
from reporting.provider.events.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class EventsCostModelCostUpdaterError(Exception):
    """EventsCostModelCostUpdater error."""


class EventsCostModelCostUpdater:
    """Apply Koku CostModel markup/discount % to pre-rated Events costs (Model A)."""

    def __init__(self, schema, provider):
        """Establish schema and provider context."""
        self._provider = provider
        self._schema = schema

    def _get_markup_rate(self):
        """Return fractional markup multiplier (e.g. 10% -> Decimal('0.10'))."""
        with CostModelDBAccessor(
            self._schema, self._provider.uuid, price_list_effective_on=None
        ) as cost_model_accessor:
            markup = cost_model_accessor.markup or {}
            return Decimal(str(markup.get("value", 0))) / Decimal(100)

    def _update_markup_cost(self, start_date, end_date):
        """Compute markup_cost = raw_cost * markup_rate on daily summary rows."""
        markup_value = self._get_markup_rate()
        with EventsReportDBAccessor(self._schema) as report_accessor:
            with schema_context(self._schema):
                bills = list(report_accessor.bills_for_provider_uuid_range(self._provider.uuid, start_date, end_date))
                bill_ids = [bill.id for bill in bills]
            if bill_ids:
                report_accessor.populate_markup_cost(markup_value, start_date, end_date, bill_ids)
            return bills

    def update_summary_cost_model_costs(self, summary_range: SummaryRangeConfig) -> None:
        """Update markup_cost and refresh UI summary tables for summary_range."""
        start_date = summary_range.start_date
        end_date = summary_range.end_date
        LOG.debug(
            log_json(
                msg="starting Events markup calculation updates",
                schema=self._schema,
                provider_uuid=self._provider.uuid,
                start_date=start_date,
                end_date=end_date,
            )
        )

        bills = self._update_markup_cost(start_date, end_date)
        with EventsReportDBAccessor(self._schema) as accessor:
            accessor.populate_ui_summary_tables(start_date, end_date, self._provider.uuid, UI_SUMMARY_TABLES)
            with schema_context(self._schema):
                now = timezone.now()
                for bill in bills:
                    bill.derived_cost_datetime = now
                    bill.save(update_fields=["derived_cost_datetime"])
