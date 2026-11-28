#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Exercise the cached GET /sources/ responses against a real cache backend."""
from unittest.mock import patch

from django.conf import settings
from django.core.cache import caches
from django.db.models.signals import post_save
from django.test.utils import override_settings
from django.urls import reverse

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.provider_manager import bulk_source_details
from api.provider.provider_manager import provider_post_save_refresh_cache
from koku.cache import bump_cache_generation
from koku.cache import SOURCES_CACHE_PREFIX
from koku.settings import CacheEnum
from sources.api.view import SourcesViewSet


@override_settings(
    ROOT_URLCONF="sources.urls",
    ENHANCED_ORG_ADMIN=True,
    CACHES={
        **settings.CACHES,
        CacheEnum.api: {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "sources-view-cache",
            "KEY_FUNCTION": "django_tenants.cache.make_key",
            "REVERSE_KEY_FUNCTION": "django_tenants.cache.reverse_key",
        },
    },
)
class SourcesCacheTests(IamTestCase):
    """The list endpoint is cached, and a generation bump drops every page of it."""

    def setUp(self):
        """Serve one OCP source through a cache that really stores responses."""
        super().setUp()
        self.api_cache = caches[CacheEnum.api]
        self.generation_cache = caches[CacheEnum.generation]
        for cache in (self.api_cache, self.generation_cache):
            cache.clear()
            self.addCleanup(cache.clear)
        self.provider = self.baker.make(Provider, type=Provider.PROVIDER_OCP, customer=self.customer, active=False)
        self.baker.make(
            Sources,
            source_uuid=self.provider.uuid,
            koku_uuid=str(self.provider.uuid),
            source_type=Provider.PROVIDER_OCP,
            org_id=self.customer.org_id,
            account_id=self.customer.account_id,
            name="sources-cache",
        )
        self.url = reverse("sources-list")

    def get_source(self, query=""):
        """Return the listed source, going through the view and its cache."""
        response = self.client.get(f"{self.url}?name=sources-cache{query}", **self.headers)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(len(body["data"]), 1, body)
        return body["data"][0]

    def assert_cache_hit(self, expected, query=""):
        """Fail if answering the request needs the database again."""
        with patch.object(SourcesViewSet, "get_queryset", side_effect=AssertionError("expected a cache hit")):
            self.assertEqual(self.get_source(query), expected)

    def assert_cache_miss(self, query=""):
        """Fail if the response comes from the cache."""
        with patch("sources.api.view.bulk_source_details", wraps=bulk_source_details) as bulk:
            source = self.get_source(query)
        bulk.assert_called_once()
        return source

    def test_list_response_is_cached(self):
        """A second identical request must not rebuild the response."""
        source = self.get_source()

        self.assert_cache_hit(source)

    def test_a_single_bump_drops_every_cached_page(self):
        """The old mechanism had to find each query string, this one does not."""
        default_page = self.get_source()
        large_page = self.get_source("&limit=1000")
        self.assert_cache_hit(default_page)
        self.assert_cache_hit(large_page, "&limit=1000")

        bump_cache_generation(self.schema_name, SOURCES_CACHE_PREFIX)

        self.assert_cache_miss()
        self.assert_cache_miss("&limit=1000")

    def test_bump_abandons_the_cached_entries_instead_of_searching_for_them(self):
        """Invalidation must not depend on walking the keyspace."""
        self.get_source()
        cached_keys = set(self.api_cache._cache)
        self.assertTrue(cached_keys)

        bump_cache_generation(self.schema_name, SOURCES_CACHE_PREFIX)

        self.assertTrue(cached_keys.issubset(set(self.api_cache._cache)))
        self.assert_cache_miss()

    def test_bump_for_another_tenant_keeps_this_tenant_cached(self):
        """Counters are per tenant, so one tenant cannot evict another."""
        source = self.get_source()

        bump_cache_generation("org2222222", SOURCES_CACHE_PREFIX)

        self.assert_cache_hit(source)

    def test_saving_a_provider_refreshes_the_listed_state(self):
        """The signal that invalidates today must still invalidate."""
        post_save.connect(provider_post_save_refresh_cache, sender=Provider)
        self.addCleanup(post_save.disconnect, provider_post_save_refresh_cache, sender=Provider)
        self.assertFalse(self.get_source()["active"])

        self.provider.active = True
        self.provider.save(update_fields=["active"])

        self.assertTrue(self.get_source()["active"])
