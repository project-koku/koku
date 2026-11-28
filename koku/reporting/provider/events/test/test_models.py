#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Events reporting models and partitioned tables."""
import re
from datetime import date
from datetime import datetime
from decimal import Decimal

from django.db import connection
from django.utils import timezone
from django_tenants.utils import schema_context
from model_bakery import baker

from koku.database import cascade_delete
from koku.pg_partition import PartitionHandlerMixin
from masu.test import MasuTestCase
from reporting.partition.models import PartitionedTable
from reporting.provider.events.models import EventsCostEntryBill
from reporting.provider.events.models import EventsCostEntryLineItemDailySummary
from reporting.provider.events.models import EventsCostSummaryByProjectP
from reporting.provider.events.models import EventsCostSummaryByServiceP
from reporting.provider.events.models import EventsCostSummaryByTenantP
from reporting.provider.events.models import EventsCostSummaryP
from reporting.provider.events.models import EventsTagsSummary
from reporting.provider.events.models import EventsTagsValues
from reporting.provider.events.models import EventsUsageSummaryByMeterP
from reporting.provider.events.models import UI_SUMMARY_TABLES
from reporting.provider.models import TenantAPIProvider

PARTITIONED_EVENT_TABLES = (
    EventsCostEntryLineItemDailySummary._meta.db_table,
    *UI_SUMMARY_TABLES,
)


class EventsModelsTest(MasuTestCase):
    """Verify Events tenant schema tables, partitioning, indexes, and cascade delete."""

    def test_partitioned_tables_have_range_partitions_and_defaults(self):
        """All six partitioned Events tables use PG RANGE partitioning with default partitions."""
        with schema_context(self.schema):
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.relname, c.relkind
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = %s
                      AND c.relname = ANY(%s)
                    """,
                    [self.schema, list(PARTITIONED_EVENT_TABLES)],
                )
                relkinds = dict(cur.fetchall())

            for table_name in PARTITIONED_EVENT_TABLES:
                with self.subTest(table=table_name):
                    self.assertEqual(relkinds.get(table_name), "p")
                    self.assertTrue(
                        PartitionedTable.objects.filter(
                            schema_name=self.schema,
                            partition_of_table_name=table_name,
                            partition_parameters__default=True,
                        ).exists(),
                        f"Missing default partition record for {table_name}",
                    )

    def test_partition_handler_creates_monthly_partitions(self):
        """PartitionHandlerMixin creates monthly partitions for daily summary and UI tables."""
        usage_date = date(2026, 11, 15)
        with schema_context(self.schema):
            PartitionHandlerMixin()._handle_partitions(
                self.schema,
                list(PARTITIONED_EVENT_TABLES),
                usage_date,
                usage_date,
            )
            for table_name in PARTITIONED_EVENT_TABLES:
                with self.subTest(table=table_name):
                    self.assertTrue(
                        PartitionedTable.objects.filter(
                            schema_name=self.schema,
                            partition_of_table_name=table_name,
                            partition_parameters__default=False,
                            partition_parameters__from="2026-11-01",
                        ).exists(),
                        f"Missing monthly partition for {table_name}",
                    )

    def test_partitioned_fk_columns_are_indexed(self):
        """Every FK column on partitioned Events tables must have an index."""
        expected_fk_cols = {
            "reporting_eventscostentrylineitem_daily_summary": "cost_entry_bill_id",
            "reporting_events_cost_summary_p": "source_uuid",
            "reporting_events_cost_summary_by_tenant_p": "source_uuid",
            "reporting_events_cost_summary_by_project_p": "source_uuid",
            "reporting_events_cost_summary_by_service_p": "source_uuid",
            "reporting_events_usage_summary_by_meter_p": "source_uuid",
        }
        with schema_context(self.schema):
            with connection.cursor() as cur:
                for table_name, fk_col in expected_fk_cols.items():
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM pg_index i
                        JOIN pg_class t ON t.oid = i.indrelid
                        JOIN pg_namespace n ON n.oid = t.relnamespace
                        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey)
                        WHERE n.nspname = %s
                          AND t.relname = %s
                          AND a.attname = %s
                        """,
                        [self.schema, table_name, fk_col],
                    )
                    idx_count = cur.fetchone()[0]
                    with self.subTest(table=table_name, column=fk_col):
                        self.assertGreater(idx_count, 0, f"FK column {table_name}.{fk_col} lacks an index")

    def test_table_names_match_provider_cascade_delete_contract(self):
        """Events table names match Provider._cascade_delete() discovery regexes."""
        normalized_type = "events"
        self.assertEqual(
            EventsCostEntryBill._meta.db_table,
            f"reporting_{normalized_type}costentrybill",
        )
        self.assertRegex(EventsCostEntryLineItemDailySummary._meta.db_table, r"_daily_summary$")
        self.assertRegex(EventsCostEntryLineItemDailySummary._meta.db_table, f"_{normalized_type}")
        for ui_table in UI_SUMMARY_TABLES:
            self.assertRegex(ui_table, rf"^reporting_{normalized_type}_")
        for tag_table in (EventsTagsSummary._meta.db_table, EventsTagsValues._meta.db_table):
            self.assertTrue(re.search(f"_{normalized_type}", tag_table))

    def test_crud_signed_corrections_and_cascade_delete(self):
        """Signed negative corrections, tags, UI summaries, and cascade_delete() work cleanly."""
        usage_date = self.dh.this_month_start.date()
        period_start = timezone.make_aware(datetime(usage_date.year, usage_date.month, 1))
        period_end = timezone.make_aware(datetime(usage_date.year, usage_date.month, 28, 23, 59, 59))

        with schema_context(self.schema):
            tenant_provider = TenantAPIProvider.objects.first()
            self.assertIsNotNone(tenant_provider)

            PartitionHandlerMixin()._handle_partitions(
                self.schema,
                list(PARTITIONED_EVENT_TABLES),
                usage_date,
                usage_date,
            )

            bill = baker.make(
                EventsCostEntryBill,
                billing_period_start=period_start,
                billing_period_end=period_end,
                provider=tenant_provider,
            )
            daily = baker.make(
                EventsCostEntryLineItemDailySummary,
                cost_entry_bill=bill,
                source_uuid=tenant_provider.uuid,
                usage_start=usage_date,
                usage_end=usage_date,
                tenant_id="tenant-acme",
                tenant_name="Acme Corp",
                project_id="proj-ai",
                project_name="AI Platform",
                user_id="alice",
                service="compute_instance",
                meter="compute",
                catalog_item="osac.vm.medium",
                instance_type="standard-4-8",
                resource_id="vm-001",
                resource_name="worker-1",
                cluster_id="cluster-prod-1",
                deployment="eu-central-1",
                cost_type="Infrastructure",
                usage_amount=Decimal("-120.500000000"),
                unit="seconds",
                raw_cost=Decimal("-1.205000000000000"),
                markup_cost=Decimal("-0.120500000000000"),
                currency="USD",
                tags={"env": "prod", "team": "finops"},
                entry_count=2,
            )
            tag_summary = baker.make(
                EventsTagsSummary,
                key="env",
                values=["prod"],
                cost_entry_bill=bill,
                tenant_id="tenant-acme",
                project_id="proj-ai",
                project_name="AI Platform",
            )
            tag_value = baker.make(
                EventsTagsValues,
                key="env",
                value="prod",
                tenant_ids=["tenant-acme"],
                project_ids=["proj-ai"],
                project_names=["AI Platform"],
            )
            ui_models = [
                baker.make(
                    EventsCostSummaryP,
                    usage_start=usage_date,
                    usage_end=usage_date,
                    raw_cost=Decimal("-1.205"),
                    markup_cost=Decimal("-0.1205"),
                    currency="USD",
                    source_uuid=tenant_provider,
                ),
                baker.make(
                    EventsCostSummaryByTenantP,
                    usage_start=usage_date,
                    usage_end=usage_date,
                    tenant_id="tenant-acme",
                    tenant_name="Acme Corp",
                    raw_cost=Decimal("-1.205"),
                    markup_cost=Decimal("-0.1205"),
                    currency="USD",
                    source_uuid=tenant_provider,
                ),
                baker.make(
                    EventsCostSummaryByProjectP,
                    usage_start=usage_date,
                    usage_end=usage_date,
                    tenant_id="tenant-acme",
                    project_id="proj-ai",
                    project_name="AI Platform",
                    raw_cost=Decimal("-1.205"),
                    markup_cost=Decimal("-0.1205"),
                    currency="USD",
                    source_uuid=tenant_provider,
                ),
                baker.make(
                    EventsCostSummaryByServiceP,
                    usage_start=usage_date,
                    usage_end=usage_date,
                    tenant_id="tenant-acme",
                    project_id="proj-ai",
                    service="compute_instance",
                    deployment="eu-central-1",
                    raw_cost=Decimal("-1.205"),
                    markup_cost=Decimal("-0.1205"),
                    currency="USD",
                    source_uuid=tenant_provider,
                ),
                baker.make(
                    EventsUsageSummaryByMeterP,
                    usage_start=usage_date,
                    usage_end=usage_date,
                    tenant_id="tenant-acme",
                    project_id="proj-ai",
                    service="compute_instance",
                    meter="compute",
                    instance_type="standard-4-8",
                    usage_amount=Decimal("-120.5"),
                    unit="seconds",
                    raw_cost=Decimal("-1.205"),
                    markup_cost=Decimal("-0.1205"),
                    currency="USD",
                    source_uuid=tenant_provider,
                ),
            ]

            refetched = EventsCostEntryLineItemDailySummary.objects.get(uuid=daily.uuid)
            self.assertEqual(refetched.raw_cost, Decimal("-1.205000000000000"))
            self.assertEqual(refetched.tags, {"env": "prod", "team": "finops"})
            self.assertEqual(refetched.user_id, "alice")
            self.assertEqual(tag_value.value, "prod")

            # Use Koku's safe cascade_delete() helper for deleting bill referenced by partitioned table.
            cascade_delete(EventsCostEntryBill, EventsCostEntryBill.objects.filter(pk=bill.pk))
            self.assertFalse(EventsCostEntryLineItemDailySummary.objects.filter(uuid=daily.uuid).exists())
            self.assertFalse(EventsTagsSummary.objects.filter(uuid=tag_summary.uuid).exists())

            # Clean up UI summary rows and tag values created in this test.
            for row in ui_models:
                row.__class__.objects.filter(id=row.id).delete()
            EventsTagsValues.objects.filter(uuid=tag_value.uuid).delete()
