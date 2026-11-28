#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for Events report data."""
import datetime
import logging
import pkgutil
from calendar import monthrange
from decimal import Decimal
from decimal import InvalidOperation

from dateutil.parser import parse
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from koku.database import SQLScriptAtomicExecutorMixin
from koku.pg_partition import PartitionHandlerMixin
from masu.database import EVENTS_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from reporting.provider.all.models import TagMapping
from reporting.provider.events.models import EventsCostEntryBill
from reporting.provider.events.models import EventsCostEntryLineItemDailySummary
from reporting.provider.events.models import UI_SUMMARY_TABLES
from reporting.provider.models import TenantAPIProvider

LOG = logging.getLogger(__name__)

BULK_INSERT_BATCH_SIZE = 1000


def _to_decimal(val, default=Decimal(0)):
    if val is None or val == "":
        return default
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _to_date(val):
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    return parse(str(val)).date()


def _month_bounds(day: datetime.date):
    last_day = monthrange(day.year, day.month)[1]
    start = datetime.datetime(day.year, day.month, 1, 0, 0, 0, tzinfo=settings.UTC)
    end = datetime.datetime(day.year, day.month, last_day, 23, 59, 59, tzinfo=settings.UTC)
    return start, end


class EventsReportDBAccessor(SQLScriptAtomicExecutorMixin, PartitionHandlerMixin, ReportDBAccessorBase):
    """Class to interact with Events reporting tables (PostgreSQL-only)."""

    def __init__(self, schema):
        """Establish the database schema association."""
        super().__init__(schema)
        self._table_map = EVENTS_REPORT_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return EventsCostEntryLineItemDailySummary

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all Events cost entry bills for the specified provider."""
        return EventsCostEntryBill.objects.filter(provider_id=provider_uuid)

    def bills_for_provider_uuid(self, provider_uuid, start_date=None):
        """Return Events cost entry bills for provider_uuid, optionally for start_date's month."""
        bills = self.get_cost_entry_bills_query_by_provider(provider_uuid)
        if start_date:
            day = _to_date(start_date)
            bill_start, _ = _month_bounds(day)
            bills = bills.filter(billing_period_start=bill_start)
        return bills

    def bills_for_provider_uuid_range(self, provider_uuid, start_date, end_date):
        """Return Events cost entry bills overlapping [start_date, end_date]."""
        start_day = _to_date(start_date)
        end_day = _to_date(end_date)
        start_month, _ = _month_bounds(start_day)
        end_month, _ = _month_bounds(end_day)
        return self.get_cost_entry_bills_query_by_provider(provider_uuid).filter(
            billing_period_start__gte=start_month,
            billing_period_start__lte=end_month,
        )

    def get_bill_query_before_date(self, expired_date):
        """Return Events cost entry bills with billing_period_start <= expired_date."""
        return EventsCostEntryBill.objects.filter(billing_period_start__lte=expired_date)

    def get_or_create_bill(
        self, provider_uuid, usage_date, provider_name="Events", provider_type=Provider.PROVIDER_EVENTS
    ):
        """Return (bill, created) for the billing month containing usage_date."""
        day = _to_date(usage_date)
        bill_start, bill_end = _month_bounds(day)
        with schema_context(self.schema):
            tenant_provider, _ = TenantAPIProvider.objects.get_or_create(
                uuid=provider_uuid,
                defaults={"name": provider_name, "type": provider_type},
            )
            return EventsCostEntryBill.objects.get_or_create(
                billing_period_start=bill_start,
                provider=tenant_provider,
                defaults={"billing_period_end": bill_end},
            )

    def replace_daily_summary_for_dates(
        self,
        provider_uuid,
        dirty_dates,
        rows,
        markup_value=Decimal(0),
        provider_name="Events",
        provider_type=Provider.PROVIDER_EVENTS,
    ):
        """Atomically replace daily summary rows for all dirty_dates (D9).

        Deletes existing rows for each dirty UTC date (so zero-net/cancelled days
        do not leave stale rows behind), then bulk-inserts replacement rows.

        Returns:
            tuple[list[int], datetime.date | None, datetime.date | None]:
                (affected_bill_ids, min_date, max_date)
        """
        parsed_dates = sorted({_to_date(d) for d in dirty_dates})
        if not parsed_dates:
            return [], None, None

        min_date = parsed_dates[0]
        max_date = parsed_dates[-1]
        partitioned_tables = [self.line_item_daily_summary_table._meta.db_table, *UI_SUMMARY_TABLES]

        with schema_context(self.schema):
            self._handle_partitions(self.schema, partitioned_tables, min_date, max_date)

            with transaction.atomic():
                bills_by_month = {}
                for d in parsed_dates:
                    month_key = (d.year, d.month)
                    if month_key not in bills_by_month:
                        bill, _ = self.get_or_create_bill(
                            provider_uuid, d, provider_name=provider_name, provider_type=provider_type
                        )
                        bills_by_month[month_key] = bill

                # Delete stale rows for every dirty date before inserting replacements.
                EventsCostEntryLineItemDailySummary.objects.filter(
                    source_uuid=provider_uuid,
                    usage_start__in=parsed_dates,
                ).delete()

                dirty_set = set(parsed_dates)
                to_create = []
                for row in rows:
                    row_date = _to_date(row["usage_date"])
                    if row_date not in dirty_set:
                        continue
                    bill = bills_by_month[(row_date.year, row_date.month)]
                    raw_cost = _to_decimal(row.get("cost_amount"), Decimal(0))
                    markup_cost = raw_cost * markup_value
                    tags = row.get("tags")
                    if not isinstance(tags, dict):
                        tags = {}
                    entry_count = row.get("entry_count")
                    to_create.append(
                        EventsCostEntryLineItemDailySummary(
                            cost_entry_bill=bill,
                            source_uuid=provider_uuid,
                            usage_start=row_date,
                            usage_end=row_date,
                            tenant_id=str(row.get("tenant_id") or ""),
                            tenant_name=row.get("tenant_name") or None,
                            project_id=row.get("project_id") or None,
                            project_name=row.get("project_name") or None,
                            user_id=row.get("user_id") or None,
                            service=str(row.get("service") or ""),
                            meter=str(row.get("meter") or ""),
                            catalog_item=row.get("catalog_item") or None,
                            instance_type=row.get("instance_type") or None,
                            resource_id=row.get("resource_id") or None,
                            resource_name=row.get("resource_name") or None,
                            cluster_id=row.get("cluster_id") or None,
                            deployment=row.get("deployment") or None,
                            cost_type=str(row.get("cost_type") or "Infrastructure"),
                            usage_amount=_to_decimal(row.get("usage_amount"), Decimal(0)),
                            unit=row.get("unit") or None,
                            raw_cost=raw_cost,
                            markup_cost=markup_cost,
                            currency=str(row.get("currency") or "USD"),
                            tags=tags,
                            entry_count=int(entry_count) if entry_count is not None else None,
                        )
                    )

                if to_create:
                    EventsCostEntryLineItemDailySummary.objects.bulk_create(
                        to_create, batch_size=BULK_INSERT_BATCH_SIZE
                    )

                bill_ids = sorted({bill.id for bill in bills_by_month.values()})
                LOG.info(
                    log_json(
                        msg="replaced Events daily summary rows",
                        schema=self.schema,
                        provider_uuid=str(provider_uuid),
                        dirty_dates=len(parsed_dates),
                        inserted_rows=len(to_create),
                        bill_ids=bill_ids,
                    )
                )
                return bill_ids, min_date, max_date

    def populate_enabled_tag_keys(self, start_date, end_date, bill_ids=None):
        """Register any newly seen Events tag keys in reporting_enabledtagkeys (preserving disabled keys)."""
        sql = """
            INSERT INTO {{schema | sqlsafe}}.reporting_enabledtagkeys (uuid, key, enabled, provider_type)
            SELECT uuid_generate_v4(), keys.key, true, 'Events'
            FROM (
                SELECT DISTINCT jsonb_object_keys(tags) AS key
                FROM {{schema | sqlsafe}}.reporting_eventscostentrylineitem_daily_summary
                WHERE usage_start >= {{start_date}}::date
                    AND usage_start <= {{end_date}}::date
                    AND tags IS NOT NULL
                    {% if bill_ids %}
                    AND cost_entry_bill_id IN {{ bill_ids | inclause }}
                    {% endif %}
            ) AS keys
            ON CONFLICT (key, provider_type) DO NOTHING;
        """
        sql_params = {
            "schema": self.schema,
            "start_date": _to_date(start_date),
            "end_date": _to_date(end_date),
            "bill_ids": bill_ids or [],
        }
        self._prepare_and_execute_raw_sql_query("reporting_enabledtagkeys", sql, sql_params, operation="INSERT")

    def update_line_item_daily_summary_with_tag_mapping(self, start_date, end_date, bill_ids=None):
        """Rewrite mapped child tag keys onto parent keys in the daily summary table."""
        with schema_context(self.schema):
            has_mappings = TagMapping.objects.filter(
                child__provider_type=Provider.PROVIDER_EVENTS, child__enabled=True
            ).exists()
        if not has_mappings:
            return
        sql = pkgutil.get_data("masu.database", "sql/events/events_tag_mapping_update_daily_summary.sql").decode(
            "utf-8"
        )
        sql_params = {
            "schema": self.schema,
            "start_date": _to_date(start_date),
            "end_date": _to_date(end_date),
            "bill_ids": bill_ids or [],
        }
        self._prepare_and_execute_raw_sql_query(
            self._table_map["line_item_daily_summary"], sql, sql_params, operation="UPDATE"
        )

    def populate_markup_cost(self, markup, start_date, end_date, bill_ids=None):
        """Set markup_cost = raw_cost * markup on Events daily summary rows."""
        with schema_context(self.schema):
            qs = EventsCostEntryLineItemDailySummary.objects.all()
            if bill_ids:
                qs = qs.filter(cost_entry_bill_id__in=bill_ids)
            if start_date:
                qs = qs.filter(usage_start__gte=_to_date(start_date))
            if end_date:
                qs = qs.filter(usage_start__lte=_to_date(end_date))
            qs.update(markup_cost=F("raw_cost") * markup)

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate the 5 lean Events UI summary tables for [start_date, end_date]."""
        start_d = _to_date(start_date)
        end_d = _to_date(end_date)
        with schema_context(self.schema):
            self._handle_partitions(self.schema, list(tables), start_d, end_d)
        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"sql/events/ui_summary/{table_name}.sql").decode("utf-8")
            sql_params = {
                "start_date": start_d,
                "end_date": end_d,
                "schema": self.schema,
                "source_uuid": str(source_uuid),
            }
            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="DELETE/INSERT")

    def populate_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate reporting_eventstags_summary and reporting_eventstags_values."""
        sql = pkgutil.get_data("masu.database", "sql/events/reporting_eventstags_summary.sql").decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "bill_ids": bill_ids or [],
            "start_date": _to_date(start_date),
            "end_date": _to_date(end_date),
        }
        self._prepare_and_execute_raw_sql_query(self._table_map["tags_summary"], sql, sql_params, operation="UPSERT")
