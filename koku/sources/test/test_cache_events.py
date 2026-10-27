"""Exact cache generation changes for the granular sources cache."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.cache import caches
from django.db import transaction
from django.test import override_settings
from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from koku.settings import CacheEnum
from sources.cache import _page_key
from sources.cache_events import advance_provider
from sources.cache_events import dynamic_source_changed_on_commit
from sources.cache_events import get_generation
from sources.cache_events import source_cache_changed


API_CACHE = {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "cost-8142-cache-events",
    "KEY_PREFIX": "api",
    "KEY_FUNCTION": "django_tenants.cache.make_key",
    "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
}


@override_settings(CACHES={**settings.CACHES, CacheEnum.api: API_CACHE})
class SourcesCacheEventsTest(IamTestCase):
    def setUp(self):
        super().setUp()
        caches[CacheEnum.api].clear()

    def test_provider_advance_does_not_change_other_provider_or_page(self):
        first = uuid4()
        second = uuid4()
        schema = self.schema_name
        with schema_context(schema):
            before_page = get_generation(schema, "page")
            before_first = get_generation(schema, f"provider:{first}")
            before_second = get_generation(schema, f"provider:{second}")

        with patch("koku.cache.invalidate_cache_for_tenant_and_cache_key", side_effect=AssertionError("scan")):
            advance_provider(schema, first)

        with schema_context(schema):
            self.assertEqual(get_generation(schema, "page"), before_page)
            self.assertNotEqual(get_generation(schema, f"provider:{first}"), before_first)
            self.assertEqual(get_generation(schema, f"provider:{second}"), before_second)

    def test_on_commit_advance_waits_for_commit_and_skips_rollback(self):
        schema = self.schema_name
        provider_uuid = uuid4()
        before = get_generation(schema, f"provider:{provider_uuid}")

        with patch("masu.processor.is_feature_flag_enabled_by_schema", return_value=True):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                dynamic_source_changed_on_commit(schema, provider_uuid)
                self.assertEqual(get_generation(schema, f"provider:{provider_uuid}"), before)
            self.assertEqual(len(callbacks), 1)
            changed = get_generation(schema, f"provider:{provider_uuid}")
            self.assertNotEqual(changed, before)

            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(ValueError), transaction.atomic():
                    dynamic_source_changed_on_commit(schema, provider_uuid)
                    raise ValueError("rollback")
            self.assertEqual(callbacks, [])
        self.assertEqual(get_generation(schema, f"provider:{provider_uuid}"), changed)

    def test_page_advance_changes_only_page_generation(self):
        schema = self.schema_name
        provider_uuid = uuid4()
        before_page = get_generation(schema, "page")
        before_provider = get_generation(schema, f"provider:{provider_uuid}")

        with (
            patch("masu.processor.is_feature_flag_enabled_by_schema", return_value=True),
            self.captureOnCommitCallbacks(execute=True),
        ):
            source_cache_changed(schema, page=True)

        self.assertNotEqual(get_generation(schema, "page"), before_page)
        self.assertEqual(get_generation(schema, f"provider:{provider_uuid}"), before_provider)

    def test_source_edit_refreshes_page_and_provider_without_scan(self):
        schema = self.schema_name
        provider_uuid = uuid4()
        before_page = get_generation(schema, "page")
        before_provider = get_generation(schema, f"provider:{provider_uuid}")
        with (
            patch("masu.processor.is_feature_flag_enabled_by_schema", return_value=True),
            patch("koku.cache.invalidate_cache_for_tenant_and_cache_key", side_effect=AssertionError("scan")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            source_cache_changed(schema, page=True, provider_uuid=provider_uuid)
            self.assertEqual(get_generation(schema, "page"), before_page)
        self.assertNotEqual(get_generation(schema, "page"), before_page)
        self.assertNotEqual(get_generation(schema, f"provider:{provider_uuid}"), before_provider)

    def test_dynamic_events_are_inert_when_flag_is_off(self):
        schema = self.schema_name
        provider_uuid = uuid4()
        before = get_generation(schema, f"provider:{provider_uuid}")
        with (
            patch("masu.processor.is_feature_flag_enabled_by_schema", return_value=False),
            self.captureOnCommitCallbacks(execute=True),
        ):
            dynamic_source_changed_on_commit(schema, provider_uuid)
        self.assertEqual(get_generation(schema, f"provider:{provider_uuid}"), before)

    def test_snapshot_key_separates_user_access_and_query(self):
        user = SimpleNamespace(uuid=uuid4(), admin=False, access={"openshift.cluster": {"read": ["a"]}})
        request = SimpleNamespace(
            user=user,
            accepted_renderer=SimpleNamespace(format="json"),
            META={"HTTP_ACCEPT": "application/json"},
            get_full_path=lambda: "/sources/?limit=1000",
        )
        initial = _page_key(request, self.schema_name)
        user.access = {"openshift.cluster": {"read": ["b"]}}
        self.assertNotEqual(_page_key(request, self.schema_name), initial)
        user.access = {"openshift.cluster": {"read": ["a"]}}
        request.get_full_path = lambda: "/sources/?limit=500"
        self.assertNotEqual(_page_key(request, self.schema_name), initial)
