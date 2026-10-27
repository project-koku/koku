"""The granular /sources/ cache keeps provider changes fresh on one URL."""
from unittest.mock import patch

from django.conf import settings
from django.core.cache import caches
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.renderers import JSONRenderer

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.provider_manager import bulk_source_details
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from koku.settings import CacheEnum
from masu.util.common import DateHelper
from reporting_common.models import CostUsageReportManifest
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep
from sources.cache import _generations
from sources.cache import get_or_fill_details
from sources.cache_events import advance_provider
from sources.cache_events import get_generation


API_CACHE = {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "cost-8142-granular-cache",
    "KEY_PREFIX": "api",
    "KEY_FUNCTION": "django_tenants.cache.make_key",
    "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
}


@override_settings(CACHES={**settings.CACHES, CacheEnum.api: API_CACHE})
class GranularSourcesListTest(IamTestCase):
    def setUp(self):
        super().setUp()
        caches[CacheEnum.api].clear()
        self.addCleanup(caches[CacheEnum.api].clear)
        self.providers = [
            self.baker.make(Provider, customer=self.customer, type=Provider.PROVIDER_OCP, active=True)
            for _ in range(2)
        ]
        for index, provider in enumerate(self.providers):
            self.baker.make(
                Sources,
                source_id=900000 + index,
                source_uuid=provider.uuid,
                koku_uuid=str(provider.uuid),
                provider=provider,
                name=f"COST-8142 test {index}",
                source_type=Provider.PROVIDER_OCP,
                account_id=self.customer.account_id,
                org_id=self.customer.org_id,
                offset=0,
                authentication={"credentials": {"cluster_id": f"cost-8142-test-{index}"}},
            )

    def _list(self):
        return self.client.get(reverse("sources-list"), {"limit": 1000}, **self.request_context["request"].META)

    def test_response_matches_legacy_and_strips_secret(self):
        source = Sources.objects.get(koku_uuid=str(self.providers[0].uuid))
        source.authentication["credentials"]["client_secret"] = "do-not-return"
        source.save()
        with patch("sources.api.view.is_feature_flag_enabled_by_schema", return_value=False):
            legacy = self._list()
        with patch("sources.api.view.is_feature_flag_enabled_by_schema", return_value=True):
            granular = self._list()
        self.assertEqual(granular.json(), legacy.json())
        self.assertNotIn("do-not-return", granular.content.decode())

    def test_same_url_refreshes_one_provider_and_reuses_other_details(self):
        first, second = self.providers
        with (
            patch("sources.api.view.is_feature_flag_enabled_by_schema", return_value=True),
            patch("sources.cache.bulk_source_details", wraps=bulk_source_details) as bulk,
            patch("sources.api.view.get_or_fill_details", wraps=get_or_fill_details) as lookup,
            patch("rest_framework.renderers.JSONRenderer.render", wraps=JSONRenderer.render, autospec=True) as render,
            patch("sources.cache._generations", wraps=_generations) as generation_reads,
        ):
            initial = self._list()
            self.assertEqual(initial.status_code, 200)
            self.assertEqual(initial["Cache-Control"], "private, no-store")
            initial_by_uuid = {str(item["uuid"]): item for item in initial.data["data"]}
            self.assertTrue(initial_by_uuid[str(first.uuid)]["active"])
            self.assertTrue(initial_by_uuid[str(second.uuid)]["active"])
            cold_generation_reads = generation_reads.call_count

            unchanged = self._list()
            self.assertEqual(unchanged.data, initial.data)
            self.assertEqual(bulk.call_count, 1)
            self.assertEqual(lookup.call_count, 1, "unchanged poll should return assembled snapshot")
            self.assertEqual(render.call_count, 1, "unchanged poll should reuse rendered response")
            self.assertEqual(generation_reads.call_count, cold_generation_reads)

            Provider.objects.filter(uuid=first.uuid).update(active=False)
            advance_provider(self.schema_name, first.uuid)
            updated = self._list()

        updated_by_uuid = {str(item["uuid"]): item for item in updated.data["data"]}
        self.assertFalse(updated_by_uuid[str(first.uuid)]["active"])
        self.assertTrue(updated_by_uuid[str(second.uuid)]["active"])
        self.assertEqual(bulk.call_count, 2)
        self.assertEqual([str(first.uuid)], [str(value) for value in bulk.call_args.args[0]])

    def test_manifest_completion_and_cost_model_edits_refresh_same_url(self):
        first = self.providers[0]
        with patch("sources.api.view.is_feature_flag_enabled_by_schema", return_value=True):
            initial = self._list()
            initial_source = next(item for item in initial.data["data"] if str(item["uuid"]) == str(first.uuid))
            self.assertFalse(initial_source["has_data"])

            with self.captureOnCommitCallbacks(execute=True):
                manifest = CostUsageReportManifest.objects.create(
                    provider=first,
                    assembly_id="cost-8142-refresh",
                    billing_period_start_datetime=DateHelper().this_month_start,
                    num_total_files=0,
                    operator_version="v4.0.0",
                )
            with self.captureOnCommitCallbacks(execute=True):
                manifest.state = {ManifestStep.PROCESSING: {ManifestState.START: timezone.now().isoformat()}}
                manifest.save(update_fields=["state"])
            processing = next(item for item in self._list().data["data"] if str(item["uuid"]) == str(first.uuid))
            self.assertEqual(processing["status"][ManifestStep.PROCESSING]["state"], "in-progress")
            with self.captureOnCommitCallbacks(execute=True):
                manifest.completed_datetime = timezone.now()
                manifest.save(update_fields=["completed_datetime"])
            completed = next(item for item in self._list().data["data"] if str(item["uuid"]) == str(first.uuid))
            self.assertTrue(completed["has_data"])
            self.assertTrue(completed["current_month_data"])
            before_housekeeping = get_generation(self.schema_name, f"provider:{first.uuid}")
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                manifest.num_total_files = 1
                manifest.save(update_fields=["num_total_files"])
            self.assertEqual(callbacks, [])
            self.assertEqual(get_generation(self.schema_name, f"provider:{first.uuid}"), before_housekeeping)

            with self.captureOnCommitCallbacks(execute=True):
                with tenant_context(self.tenant):
                    model = CostModel.objects.create(
                        name="first name", description="", source_type=Provider.PROVIDER_OCP
                    )
                    mapping = CostModelMap.objects.create(provider_uuid=first.uuid, cost_model=model)
            attached = next(item for item in self._list().data["data"] if str(item["uuid"]) == str(first.uuid))
            self.assertEqual(attached["cost_models"][0]["name"], "first name")

            with self.captureOnCommitCallbacks(execute=True):
                with tenant_context(self.tenant):
                    model.name = "second name"
                    model.save(update_fields=["name"])
            renamed = next(item for item in self._list().data["data"] if str(item["uuid"]) == str(first.uuid))
            self.assertEqual(renamed["cost_models"][0]["name"], "second name")

            with self.captureOnCommitCallbacks(execute=True):
                with tenant_context(self.tenant):
                    mapping.delete()
            detached = next(item for item in self._list().data["data"] if str(item["uuid"]) == str(first.uuid))
            self.assertEqual(detached["cost_models"], [])
