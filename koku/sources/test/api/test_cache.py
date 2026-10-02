#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Exercise the cached sources responses that control the UI's no-data state."""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.cache import caches
from django.db import transaction
from django.test import override_settings
from django.urls import reverse
from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from cost_models.cost_model_manager import CostModelManager
from cost_models.models import CostModel
from koku.cache import SOURCES_CACHE_PREFIX
from koku.settings import CacheEnum
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.processor.tasks import mark_manifest_complete
from reporting_common.models import CostUsageReportManifest
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep
from sources.api.view import SourcesViewSet


@override_settings(
    ROOT_URLCONF="sources.urls",
    ENHANCED_ORG_ADMIN=True,
    CACHES={
        **settings.CACHES,
        CacheEnum.api: {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "sources-response-regression",
            "KEY_FUNCTION": "django_tenants.cache.make_key",
            "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
        },
    },
)
class SourcesCacheTests(IamTestCase):
    """Use real views, database writes and cache eviction, without a browser."""

    def setUp(self):
        super().setUp()
        self.cache = caches[CacheEnum.api]
        self.cache.clear()
        self.addCleanup(self.cache.clear)
        self.provider = self.baker.make(Provider, type=Provider.PROVIDER_OCP, customer=self.customer, active=False)
        self.source = self.baker.make(
            Sources,
            source_uuid=self.provider.uuid,
            koku_uuid=self.provider.uuid,
            source_type=Provider.PROVIDER_OCP,
            org_id=self.customer.org_id,
            account_id=self.customer.account_id,
            name="sources-cache-regression",
        )
        self.manifest = self.baker.make(
            CostUsageReportManifest,
            provider=self.provider,
            billing_period_start_datetime=self.dh.this_month_start,
            completed_datetime=None,
            operator_version="4.0.0",
            state={},
        )
        self.url = reverse("sources-list") + "?type=OCP&name=sources-cache-regression"
        self.accessor = ReportManifestDBAccessor()

    def get_source(self, detail=False):
        url = reverse("sources-detail", kwargs={"pk": self.source.source_uuid}) if detail else self.url
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        if detail:
            return body
        self.assertEqual(len(body["data"]), 1, body)
        return body["data"][0]

    def assert_cache_hit(self, expected):
        with patch.object(SourcesViewSet, "get_queryset", side_effect=AssertionError("Expected a cache hit")):
            self.assertEqual(self.get_source(), expected)

    def test_ocp_completion_refreshes_ui_data_flags(self):
        before = self.get_source()
        self.assertFalse(before["has_data"])
        self.assertFalse(before["current_month_data"])
        self.assertFalse(before["previous_month_data"])
        self.assert_cache_hit(before)

        # Run the actual pipeline completion task, including its provider update.
        with self.captureOnCommitCallbacks(execute=True):
            mark_manifest_complete(
                self.schema_name, Provider.PROVIDER_OCP, str(self.provider.uuid), manifest_list=[self.manifest.id]
            )

        self.manifest.refresh_from_db()
        self.assertIsNotNone(self.manifest.completed_datetime)
        after = self.get_source()
        self.assertTrue(after["has_data"])
        self.assertTrue(after["current_month_data"])
        self.assertFalse(after["previous_month_data"])
        self.assertEqual(after, self.get_source(detail=True))
        self.assert_cache_hit(after)

    def test_previous_month_completion_refreshes_ui_data_flags(self):
        self.manifest.billing_period_start_datetime = self.dh.last_month_start
        self.manifest.save()
        self.assertFalse(self.get_source()["previous_month_data"])
        with self.captureOnCommitCallbacks(execute=True):
            self.accessor.mark_manifests_as_completed([self.manifest.id])
        after = self.get_source()
        self.assertTrue(after["has_data"])
        self.assertTrue(after["previous_month_data"])
        self.assertFalse(after["current_month_data"])

    def test_old_completed_data_does_not_open_current_month_dashboard(self):
        self.manifest.billing_period_start_datetime = (self.dh.last_month_start - timedelta(days=1)).replace(day=1)
        self.manifest.save()
        self.get_source()
        with self.captureOnCommitCallbacks(execute=True):
            self.accessor.mark_manifests_as_completed([self.manifest.id])
        after = self.get_source()
        self.assertTrue(after["has_data"])
        self.assertFalse(after["current_month_data"])
        self.assertFalse(after["previous_month_data"])
        self.assertEqual(after, self.get_source(detail=True))

    def test_processing_and_summary_transitions_refresh_status(self):
        for step in (ManifestStep.PROCESSING, ManifestStep.SUMMARY):
            for interval, expected in ((ManifestState.START, "in-progress"), (ManifestState.END, "complete")):
                with self.subTest(step=step, interval=interval):
                    self.assert_cache_hit(self.get_source())
                    with self.captureOnCommitCallbacks(execute=True):
                        self.accessor.update_manifest_state(step, interval, self.manifest.id)
                    self.assertEqual(self.get_source()["status"][step]["state"], expected)

    def test_new_manifest_refreshes_last_payload_and_status(self):
        before = self.get_source()
        with self.captureOnCommitCallbacks(execute=True):
            manifest = self.baker.make(
                CostUsageReportManifest,
                provider=self.provider,
                billing_period_start_datetime=self.dh.this_month_start,
                creation_datetime=self.manifest.creation_datetime + timedelta(minutes=1),
                completed_datetime=None,
                operator_version="4.0.0",
                state={},
            )
        after = self.get_source()
        self.assertNotEqual(after["last_payload_received_at"], before["last_payload_received_at"])
        self.assertEqual(after["status"][ManifestStep.PROCESSING]["state"], "pending")
        self.assertEqual(after, self.get_source(detail=True))
        self.assertIsNone(manifest.completed_datetime)

    def test_invalidation_waits_for_commit(self):
        before = self.get_source()
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                self.accessor.mark_manifests_as_completed([self.manifest.id])
                # Other DB connections still see the old row here. Evicting now
                # would let their reads refill the cache with pre-commit values.
                self.assert_cache_hit(before)
        self.assertTrue(self.get_source()["current_month_data"])

    def test_cache_failure_does_not_fail_committed_manifest_update(self):
        later_callback_ran = []
        with (
            patch(
                "koku.cache.invalidate_cache_for_tenant_and_cache_key",
                side_effect=ConnectionError("Redis unavailable"),
            ) as invalidate,
            self.assertLogs("koku.cache", level="ERROR") as logged,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.accessor.mark_manifests_as_completed([self.manifest.id])
            transaction.on_commit(lambda: later_callback_ran.append(True))

        self.manifest.refresh_from_db()
        self.assertIsNotNone(self.manifest.completed_datetime)
        invalidate.assert_called_once_with(self.schema_name, SOURCES_CACHE_PREFIX)
        self.assertEqual(later_callback_ran, [True])
        self.assertIn(self.schema_name, logged.output[0])
        self.assertIn("Redis unavailable", logged.output[0])

    def test_rollback_keeps_cached_committed_state(self):
        before = self.get_source()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaisesMessage(ValueError, "rollback"):
                with transaction.atomic():
                    self.accessor.mark_manifests_as_completed([self.manifest.id])
                    raise ValueError("rollback")
        self.manifest.refresh_from_db()
        self.assertIsNone(self.manifest.completed_datetime)
        self.assert_cache_hit(before)

    def test_completion_preserves_other_tenant_cache(self):
        with schema_context("org2222222"):
            self.cache.set("sources-other-tenant", "keep")
        self.get_source()
        with self.captureOnCommitCallbacks(execute=True):
            self.accessor.mark_manifests_as_completed([self.manifest.id])
        self.assertTrue(self.get_source()["has_data"])
        with schema_context("org2222222"):
            self.assertEqual(self.cache.get("sources-other-tenant"), "keep")

    def test_cost_model_assignment_detachment_and_deletion_refresh_list(self):
        with schema_context(self.schema_name):
            model = self.baker.make(CostModel, source_type=Provider.PROVIDER_OCP, rates=[])
        self.assertEqual(self.get_source()["cost_models"], [])
        for uuids in ([str(self.provider.uuid)], [], [str(self.provider.uuid)]):
            with self.subTest(uuids=uuids):
                with self.captureOnCommitCallbacks(execute=True), schema_context(self.schema_name):
                    CostModelManager(cost_model_uuid=model.uuid).update_provider_uuids(uuids)
                models = self.get_source()["cost_models"]
                self.assertEqual([item["uuid"] for item in models], [str(model.uuid)] if uuids else [])
                self.assert_cache_hit(self.get_source())
        with self.captureOnCommitCallbacks(execute=True), schema_context(self.schema_name):
            model.delete()
        self.assertEqual(self.get_source()["cost_models"], [])
