#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Removes expired Events report data from database."""
import logging
from datetime import date

from django_tenants.utils import schema_context

from api.common import log_json
from koku.database import cascade_delete
from koku.pg_partition import drop_expired_partitions
from masu.database.events_report_db_accessor import EventsReportDBAccessor
from reporting.provider.events.models import UI_SUMMARY_TABLES

LOG = logging.getLogger(__name__)


class EventsReportDBCleanerError(Exception):
    """Raise an error during Events report cleaning."""


class EventsReportDBCleaner:
    """Class to remove expired or deleted-provider Events report data."""

    def __init__(self, schema):
        """Establish the database schema association."""
        self._schema = schema

    def purge_expired_report_data(self, expired_date=None, provider_uuid=None, simulate=False):
        """Remove report data before expired_date or for a specific provider_uuid."""
        LOG.info(
            log_json(
                msg="calling purge_expired_report_data for Events",
                schema=self._schema,
                provider_uuid=provider_uuid,
            )
        )

        if (expired_date is None and provider_uuid is None) or (
            expired_date is not None and provider_uuid is not None
        ):
            raise EventsReportDBCleanerError("This method must be called with either expired_date or provider_uuid")

        if expired_date is not None:
            return self.purge_expired_report_data_by_date(expired_date, simulate=simulate)

        with EventsReportDBAccessor(self._schema) as accessor:
            bill_objects = accessor.get_cost_entry_bills_query_by_provider(provider_uuid)

        removed_items = []
        with schema_context(self._schema):
            for bill in bill_objects.all():
                removed_items.append(
                    {"removed_provider_uuid": bill.provider_id, "billing_period_start": str(bill.billing_period_start)}
                )
            if not simulate:
                cascade_delete(bill_objects.query.model, bill_objects)

        return removed_items

    def purge_expired_report_data_by_date(self, expired_date, simulate=False):
        """Drop expired monthly partitions for Events tables on or before expired_date."""
        partition_from = str(date(expired_date.year, expired_date.month, 1))
        with EventsReportDBAccessor(self._schema) as accessor:
            all_bill_objects = list(accessor.get_bill_query_before_date(expired_date).all())
            table_names = [accessor.line_item_daily_summary_table._meta.db_table, *UI_SUMMARY_TABLES]

        removed_items = []
        with schema_context(self._schema):
            if not simulate:
                LOG.info(
                    log_json(
                        msg="deleting Events table partitions",
                        schema=self._schema,
                        tables=table_names,
                        partitions=partition_from,
                    )
                )
                del_count = drop_expired_partitions(self._schema, table_names, partition_from)
                LOG.info(
                    log_json(msg="deleted Events table partitions", schema=self._schema, records_deleted=del_count)
                )

            for bill in all_bill_objects:
                removed_items.append(
                    {"removed_provider_uuid": bill.provider_id, "billing_period_start": str(bill.billing_period_start)}
                )

        return removed_items
