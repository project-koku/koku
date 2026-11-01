#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the provider advisory locks sync_rate_table takes before deleting stale Rate rows (COST-8113).

Deleting a Rate cascades into rates_to_usage for every provider on every cost
model attached to the price list. RTU writers serialize per provider with a
session-level pg_advisory_lock(hashtext(provider_uuid)); sync_rate_table takes
transaction-level locks on the same keys so the delete cannot interleave with
a writer, and so the locks last until the caller's outermost transaction ends.

These tests use TransactionTestCase so the outer transaction really commits,
and a second raw connection ("probe") to observe and hold advisory locks the
way a concurrent RTU writer would.
"""
from datetime import date
from unittest.mock import patch
from uuid import uuid4

import django.test
import psycopg2
from django.db import connection
from django.db import transaction
from django_tenants.utils import schema_context

from api.metrics import constants as metric_constants
from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.models import PriceList
from cost_models.models import PriceListCostModelMap
from cost_models.models import Rate
from cost_models.rate_sync import RateSyncLockTimeout
from cost_models.rate_sync import sync_rate_table

FLAG_TARGET = "cost_models.rate_sync.is_rate_sync_provider_lock_enabled"


class RateSyncProviderLockTest(django.test.TransactionTestCase):
    """sync_rate_table locks every provider reachable from the price list while it deletes stale rates."""

    def _fixture_teardown(self):
        """Skip the TRUNCATE flush; django-tenants' FK graph breaks it. tearDown cleans up instead."""

    def setUp(self):
        from koku.koku_test_runner import KokuTestRunner

        self.schema = KokuTestRunner.schema
        self.provider_uuids = [uuid4(), uuid4()]
        self.rate_data = {
            "metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR},
            "tiered_rates": [{"unit": "USD", "value": 0.22}],
            "cost_type": "Infrastructure",
        }
        with schema_context(self.schema):
            self.price_list = PriceList.objects.create(
                name=f"cost-8113-pl-{uuid4().hex[:8]}",
                currency="USD",
                effective_start_date=date(2026, 1, 1),
                effective_end_date=date(2099, 12, 31),
                rates=[],
            )
            self.cost_model = CostModel.objects.create(
                name=f"cost-8113-cm-{uuid4().hex[:8]}",
                description="COST-8113 lock test",
                source_type=Provider.PROVIDER_OCP,
                rates=[],
            )
            PriceListCostModelMap.objects.create(price_list=self.price_list, cost_model=self.cost_model, priority=1)
            for provider_uuid in self.provider_uuids:
                CostModelMap.objects.create(cost_model=self.cost_model, provider_uuid=provider_uuid)
            with patch(FLAG_TARGET, return_value=False):
                enriched = sync_rate_table(self.price_list, [dict(self.rate_data)])
            self.rate_uuid = enriched[0]["rate_id"]

        params = connection.settings_dict
        self.probe = psycopg2.connect(
            dbname=params["NAME"],
            user=params["USER"],
            password=params["PASSWORD"],
            host=params["HOST"],
            port=params["PORT"],
        )
        self.probe.autocommit = True

    def tearDown(self):
        self.probe.close()
        with schema_context(self.schema):
            Rate.objects.filter(price_list=self.price_list).delete()
            CostModelMap.objects.filter(cost_model=self.cost_model).delete()
            PriceListCostModelMap.objects.filter(price_list=self.price_list).delete()
            CostModel.objects.filter(uuid=self.cost_model.uuid).delete()
            PriceList.objects.filter(uuid=self.price_list.uuid).delete()

    def _probe_can_lock(self, provider_uuid):
        """Return True if another session could take this provider's lock right now (and release it again)."""
        with self.probe.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [str(provider_uuid)])
            acquired = cursor.fetchone()[0]
            if acquired:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [str(provider_uuid)])
        return acquired

    def _probe_hold_lock(self, provider_uuid):
        """Hold this provider's session-level lock from another connection, like a running RTU writer."""
        with self.probe.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [str(provider_uuid)])

    def _advisory_locks_held_by_this_backend(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid() AND granted"
            )
            return cursor.fetchone()[0]

    def _rate_exists(self):
        with schema_context(self.schema):
            return Rate.objects.filter(uuid=self.rate_uuid).exists()

    def test_locks_held_until_outer_transaction_commits(self):
        """The locks outlive sync_rate_table and are released only when the caller's transaction ends.

        CostModelManager.create/update and PriceListViewSet._ensure_rate_sync call
        sync_rate_table inside their own transaction, so the cascade delete stays
        uncommitted after sync_rate_table returns. Releasing the locks at that
        point would let an RTU writer insert against a Rate row that is about to
        disappear.
        """
        with patch(FLAG_TARGET, return_value=True), schema_context(self.schema):
            with transaction.atomic():
                sync_rate_table(self.price_list, [])
                for provider_uuid in self.provider_uuids:
                    self.assertFalse(self._probe_can_lock(provider_uuid), f"{provider_uuid} unlocked before commit")
            for provider_uuid in self.provider_uuids:
                self.assertTrue(self._probe_can_lock(provider_uuid), f"{provider_uuid} still locked after commit")
        self.assertFalse(self._rate_exists())

    def test_lock_timeout_raises_conflict_and_leaves_no_locks(self):
        """A writer holding one provider's lock makes sync_rate_table fail fast with 409 and roll back.

        The other provider's lock, if already taken, must not leak: there is no
        unlock statement that could fail on an aborted transaction.
        """
        self._probe_hold_lock(max(self.provider_uuids, key=str))
        with (
            patch(FLAG_TARGET, return_value=True),
            patch("cost_models.rate_sync.RATE_SYNC_LOCK_TIMEOUT_MS", 200),
            schema_context(self.schema),
        ):
            with transaction.atomic():
                with self.assertRaises(RateSyncLockTimeout) as ctx:
                    sync_rate_table(self.price_list, [])
                # The caller's transaction is still usable and holds nothing.
                self.assertEqual(self._advisory_locks_held_by_this_backend(), 0)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertTrue(self._rate_exists())
        self.assertTrue(self._probe_can_lock(min(self.provider_uuids, key=str)))

    def test_no_locks_needed_when_no_rates_are_deleted(self):
        """Updating or adding rates cannot break the rates_to_usage FK, so it never waits on writers."""
        for provider_uuid in self.provider_uuids:
            self._probe_hold_lock(provider_uuid)
        unchanged = {**self.rate_data, "rate_id": self.rate_uuid}
        added = {**self.rate_data, "cost_type": "Supplementary"}
        with (
            patch(FLAG_TARGET, return_value=True),
            patch("cost_models.rate_sync.RATE_SYNC_LOCK_TIMEOUT_MS", 200),
            schema_context(self.schema),
        ):
            sync_rate_table(self.price_list, [unchanged, added])
            self.assertEqual(Rate.objects.filter(price_list=self.price_list).count(), 2)

    def test_flag_off_deletes_without_locking(self):
        """With the flag off, sync_rate_table behaves as before and ignores provider locks."""
        for provider_uuid in self.provider_uuids:
            self._probe_hold_lock(provider_uuid)
        with patch(FLAG_TARGET, return_value=False), schema_context(self.schema):
            sync_rate_table(self.price_list, [])
        self.assertFalse(self._rate_exists())
