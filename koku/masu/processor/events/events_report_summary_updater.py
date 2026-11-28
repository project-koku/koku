#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates Events UI summary, tag summary, and markup tables in PostgreSQL."""
import logging
from decimal import Decimal

from django.utils import timezone
from django_tenants.utils import schema_context

from api.common import log_json
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.events_report_db_accessor import EventsReportDBAccessor
from reporting.provider.events.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class EventsReportSummaryUpdater:
    """Refresh Events tag keys, tag mappings, markup, UI summaries, and tag summaries."""

    def __init__(self, schema, provider, manifest=None):
        """Establish schema, provider, and optional manifest context."""
        self._schema = schema
        self._provider = provider
        self._manifest = manifest

    def update_summary_tables(self, start_date, end_date, invoice_month=None):
        """Run PostgreSQL summarization for Events across [start_date, end_date]."""
        with CostModelDBAccessor(
            self._schema, self._provider.uuid, price_list_effective_on=None
        ) as cost_model_accessor:
            markup = cost_model_accessor.markup or {}
            markup_value = Decimal(str(markup.get("value", 0))) / Decimal(100)

        with EventsReportDBAccessor(self._schema) as accessor:
            with schema_context(self._schema):
                bills = list(accessor.bills_for_provider_uuid_range(self._provider.uuid, start_date, end_date))
                bill_ids = [bill.id for bill in bills]

            accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            accessor.update_line_item_daily_summary_with_tag_mapping(start_date, end_date, bill_ids)
            if bill_ids:
                accessor.populate_markup_cost(markup_value, start_date, end_date, bill_ids)
            accessor.populate_ui_summary_tables(start_date, end_date, self._provider.uuid, UI_SUMMARY_TABLES)
            accessor.populate_tags_summary_table(bill_ids, start_date, end_date)

            now = timezone.now()
            with schema_context(self._schema):
                for bill in bills:
                    if bill.summary_data_creation_datetime is None:
                        bill.summary_data_creation_datetime = now
                    bill.summary_data_updated_datetime = now
                    bill.derived_cost_datetime = now
                    bill.save(
                        update_fields=[
                            "summary_data_creation_datetime",
                            "summary_data_updated_datetime",
                            "derived_cost_datetime",
                        ]
                    )

        LOG.info(
            log_json(
                msg="Events summary tables updated",
                schema=self._schema,
                provider_uuid=str(self._provider.uuid),
                start_date=str(start_date),
                end_date=str(end_date),
            )
        )
        return str(start_date), str(end_date)
