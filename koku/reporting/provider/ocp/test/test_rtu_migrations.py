#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for rates_to_usage schema migration 0353 (DDL deferred from no-op 0352)."""
from datetime import date
from decimal import Decimal

from django.db import connection
from django.db import transaction
from django.test import TransactionTestCase
from django_tenants.utils import tenant_context

from api.models import Tenant
from api.provider.models import Provider
from api.utils import DateHelper
from cost_models.models import CostModel
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from koku.pg_partition import PartitionHandlerMixin
from masu.test import MasuTestCase
from reporting.models import TenantAPIProvider
from reporting.provider.ocp.models import RatesToUsage

MIGRATE_FROM = ("reporting", "0352_rtu_schema_improvements")
MIGRATE_TO = ("reporting", "0353_rtu_schema_improvements")


def _latest_reporting_migration():
    """Return the current leaf migration node for the ``reporting`` app.

    Deliberately dynamic (rather than hardcoded to 0353) so this suite keeps
    working as later migrations (e.g. RTU capacity columns) are stacked on
    top of 0353_rtu_schema_improvements.
    """
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    return executor.loader.graph.leaf_nodes("reporting")[0]


class _RatesToUsageMigrationMixin:
    """Shared helpers for RTU migration tests."""

    # Model reflecting whatever migration state _run_migration() last left
    # the DB in. Migrations beyond MIGRATE_TO (0353) may add columns to
    # rates_to_usage, so ORM writes performed while intentionally parked at
    # an older migration state must use a matching historical model rather
    # than the current (fuller) RatesToUsage class, or INSERTs will
    # reference columns that don't exist yet at that point in the graph.
    _rtu_model = RatesToUsage

    def _run_migration(self, target):
        """Run migration to target state within the tenant schema."""
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        plan = executor.migration_plan([target])
        if any(backwards for _, backwards in plan):
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("TRUNCATE TABLE rates_to_usage")
            except Exception:
                pass
        state = executor.migrate([target])
        executor.loader.build_graph()
        self._rtu_model = state.apps.get_model("reporting", "RatesToUsage")

    def _ensure_rtu_partition(self, usage_start):
        PartitionHandlerMixin()._handle_partitions(
            self.schema,
            ["rates_to_usage"],
            usage_start,
            usage_start,
        )

    def _create_rtu_row(self, *, rate=None, cost_model=None, usage_start=None):
        usage_start = usage_start or self.dh.this_month_start.date()
        self._ensure_rtu_partition(usage_start)
        source = TenantAPIProvider.objects.get(uuid=self.ocp_provider_uuid)
        return self._rtu_model.objects.create(
            rate=rate,
            cost_model=cost_model,
            source_uuid=source,
            usage_start=usage_start,
            usage_end=usage_start,
            cluster_id=self.ocp_cluster_id,
            custom_name="CPU usage",
            metric_type="CPU",
        )

    def _create_cost_model_rate(self, name="RTU Migration CM"):
        cost_model = CostModel.objects.create(
            name=name,
            description="Test",
            source_type="OCP",
            rates=[],
        )
        price_list = PriceList.objects.create(
            name=f"{name} prices",
            description="Test",
            currency="USD",
            effective_start_date=date(2026, 3, 1),
            effective_end_date=date(2099, 12, 31),
            enabled=True,
            version=1,
            rates=[],
        )
        PriceListCostModelMap.objects.create(
            price_list=price_list,
            cost_model=cost_model,
            priority=1,
        )
        rate = Rate.objects.create(
            price_list=price_list,
            custom_name="CPU usage",
            metric="cpu_core_usage_per_hour",
            metric_type="CPU",
            cost_type="Infrastructure",
            default_rate=Decimal("0.01"),
        )
        return cost_model, rate

    def _index_names(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT indexname
                FROM pg_indexes
                WHERE schemaname = %s
                  AND indexname = ANY(%s)
                """,
                (
                    self.schema,
                    ["ratestousage_rate_id_idx", "ratestousage_cost_model_id_idx"],
                ),
            )
            return {row[0] for row in cursor.fetchall()}

    def _duplicate_index_groups(self):
        """Return index groups that share the same column definition (duplicates)."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT array_agg(i.indexname ORDER BY i.indexname) AS index_names
                FROM pg_indexes i
                JOIN pg_class c ON c.relname = i.indexname
                JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = i.schemaname
                WHERE i.schemaname = %s
                  AND i.tablename = 'rates_to_usage'
                  AND i.indexname NOT LIKE '%%pkey%%'
                GROUP BY regexp_replace(
                    pg_get_indexdef(c.oid),
                    '^CREATE (UNIQUE )?INDEX [^ ]+ ',
                    'CREATE INDEX '
                )
                HAVING count(*) > 1
                """,
                (self.schema,),
            )
            return [row[0] for row in cursor.fetchall()]

    def _rtu_auto_named_fk_indexes(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = %s
                  AND tablename = 'rates_to_usage'
                  AND indexname IN (
                      'rates_to_usage_rate_id_idx',
                      'rates_to_usage_cost_model_id_idx',
                      'rates_to_usage_usage_start_source_uuid_report_period_id_idx'
                  )
                """,
                (self.schema,),
            )
            return {row[0] for row in cursor.fetchall()}

    def _restore_latest_migration(self):
        """Re-apply latest migration after tests that roll back (KEEPDB=True)."""
        with tenant_context(self.tenant):
            self._run_migration(_latest_reporting_migration())

    def _cleanup_rtu_migration_fixtures(self):
        with tenant_context(self.tenant):
            CostModel.objects.filter(name__startswith="RTU ").delete()

    def tearDown(self):
        # Restore full schema *before* cleanup: the CostModel delete below
        # cascades through Django's live RatesToUsage model (all columns),
        # so the DB must already be back at the latest migration or the
        # cascade SELECT will reference columns that don't exist yet.
        self._restore_latest_migration()
        self._cleanup_rtu_migration_fixtures()
        super().tearDown()


class RatesToUsageTruncateMigrationTest(_RatesToUsageMigrationMixin, TransactionTestCase):
    """TRUNCATE migration must run outside TestCase's atomic block."""

    def setUp(self):
        self.schema = "org1234567"
        self.tenant = Tenant.objects.get(schema_name=self.schema)
        self.dh = DateHelper()
        self.ocp_provider = Provider.objects.get(
            type=Provider.PROVIDER_OCP, authentication__credentials__cluster_id="OCP-on-Prem"
        )
        self.ocp_provider_uuid = str(self.ocp_provider.uuid)
        self.ocp_cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")

    def _fixture_teardown(self):
        """Skip global TRUNCATE flush; django-tenants FK graph breaks TransactionTestCase flush."""

    def test_0353_truncates_rates_to_usage(self):
        """Migration 0353 removes all existing RTU rows."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            cost_model, rate = self._create_cost_model_rate()
            self._create_rtu_row(rate=rate, cost_model=cost_model)
            self.assertEqual(RatesToUsage.objects.count(), 1)

            self._run_migration(MIGRATE_TO)

            self.assertEqual(RatesToUsage.objects.count(), 0)


class RatesToUsageMigrationTest(_RatesToUsageMigrationMixin, MasuTestCase):
    """Test RTU index and CASCADE FK migrations."""

    def test_0353_adds_fk_indexes(self):
        """Migration 0353 creates indexes on rate_id and cost_model_id."""
        with tenant_context(self.tenant):
            # Roll back and re-apply so DDL runs even when django_migrations
            # already records 0353 (e.g. CI tenant setup vs MigrationExecutor state).
            self._run_migration(MIGRATE_FROM)
            self._run_migration(MIGRATE_TO)
            self.assertEqual(
                self._index_names(),
                {"ratestousage_rate_id_idx", "ratestousage_cost_model_id_idx"},
            )

    def test_0353_drops_duplicate_auto_named_indexes(self):
        """Migration 0353 keeps ratestousage_* indexes and removes Django auto-named duplicates."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            self._run_migration(MIGRATE_TO)
            self.assertEqual(self._rtu_auto_named_fk_indexes(), set())
            self.assertEqual(self._duplicate_index_groups(), [])

    def test_0353_cascade_deletes_rtu_when_rate_deleted(self):
        """Migration 0353 CASCADE removes RTU rows when a Rate is deleted."""
        with tenant_context(self.tenant):
            # Ensure at least 0353 has run, without forcing an exact match:
            # rate.delete() cascades via Django's live RatesToUsage model
            # (all columns), so rolling back past later additive migrations
            # (e.g. RTU capacity columns) would break the ORM-level collect.
            self._run_migration(_latest_reporting_migration())
            cost_model, rate = self._create_cost_model_rate(name="RTU Rate CASCADE CM")
            rtu = self._create_rtu_row(rate=rate, cost_model=cost_model)
            rtu_uuid = rtu.uuid

            rate.delete()

            self.assertFalse(RatesToUsage.objects.filter(uuid=rtu_uuid).exists())

    def test_0353_cascade_deletes_rtu_when_cost_model_deleted(self):
        """Migration 0353 CASCADE removes RTU rows when a CostModel is deleted."""
        with tenant_context(self.tenant):
            # See test_0353_cascade_deletes_rtu_when_rate_deleted: use latest,
            # not an exact MIGRATE_TO match, so ORM-level cascade collection
            # matches whatever columns the live RatesToUsage model expects.
            self._run_migration(_latest_reporting_migration())
            cost_model, rate = self._create_cost_model_rate(name="RTU CM CASCADE CM")
            rtu = self._create_rtu_row(rate=rate, cost_model=cost_model)
            rtu_uuid = rtu.uuid

            cost_model.delete()

            self.assertFalse(RatesToUsage.objects.filter(uuid=rtu_uuid).exists())
