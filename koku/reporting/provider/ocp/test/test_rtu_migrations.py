#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for rates_to_usage schema migrations 0352 and 0353."""
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

MIGRATE_FROM = ("reporting", "0351_create_ocp_cost_breakdown_p")
MIGRATE_TO_0352 = ("reporting", "0352_rtu_truncate_and_fk_indexes")
MIGRATE_TO_0353 = ("reporting", "0353_rtu_fk_cascade")
MIGRATE_TO_0354 = ("reporting", "0354_rtu_provider_report_period_fk")


class _RatesToUsageMigrationMixin:
    """Shared helpers for RTU migration tests."""

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
        executor.migrate([target])
        executor.loader.build_graph()

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
        return RatesToUsage.objects.create(
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

    def _restore_latest_migration(self):
        """Re-apply latest migration after tests that roll back (KEEPDB=True)."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_TO_0354)

    def _cleanup_rtu_migration_fixtures(self):
        with tenant_context(self.tenant):
            CostModel.objects.filter(name__startswith="RTU ").delete()

    def tearDown(self):
        self._cleanup_rtu_migration_fixtures()
        self._restore_latest_migration()
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

    def test_0352_truncates_rates_to_usage(self):
        """Migration 0352 removes all existing RTU rows."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_FROM)
            cost_model, rate = self._create_cost_model_rate()
            self._create_rtu_row(rate=rate, cost_model=cost_model)
            self.assertEqual(RatesToUsage.objects.count(), 1)

            self._run_migration(MIGRATE_TO_0352)

            self.assertEqual(RatesToUsage.objects.count(), 0)


class RatesToUsageMigrationTest(_RatesToUsageMigrationMixin, MasuTestCase):
    """Test RTU index and CASCADE FK migrations."""

    def test_0352_adds_fk_indexes(self):
        """Migration 0352 creates indexes on rate_id and cost_model_id."""
        with tenant_context(self.tenant):
            # Roll back and re-apply 0352 so AddIndex runs even when django_migrations
            # already records 0352+ (e.g. CI tenant setup vs MigrationExecutor state).
            self._run_migration(MIGRATE_FROM)
            self._run_migration(MIGRATE_TO_0352)
            self.assertEqual(
                self._index_names(),
                {"ratestousage_rate_id_idx", "ratestousage_cost_model_id_idx"},
            )

    def test_0353_cascade_deletes_rtu_when_rate_deleted(self):
        """Migration 0353 CASCADE removes RTU rows when a Rate is deleted."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_TO_0354)
            cost_model, rate = self._create_cost_model_rate(name="RTU Rate CASCADE CM")
            rtu = self._create_rtu_row(rate=rate, cost_model=cost_model)
            rtu_uuid = rtu.uuid

            rate.delete()

            self.assertFalse(RatesToUsage.objects.filter(uuid=rtu_uuid).exists())

    def test_0353_cascade_deletes_rtu_when_cost_model_deleted(self):
        """Migration 0353 CASCADE removes RTU rows when a CostModel is deleted."""
        with tenant_context(self.tenant):
            self._run_migration(MIGRATE_TO_0354)
            cost_model, rate = self._create_cost_model_rate(name="RTU CM CASCADE CM")
            rtu = self._create_rtu_row(rate=rate, cost_model=cost_model)
            rtu_uuid = rtu.uuid

            cost_model.delete()

            self.assertFalse(RatesToUsage.objects.filter(uuid=rtu_uuid).exists())
