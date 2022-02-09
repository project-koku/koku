#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test view caching functions."""
import logging
import random

from django.core.cache import caches
from django.test.utils import override_settings

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from koku.cache import AWS_CACHE_PREFIX
from koku.cache import AZURE_CACHE_PREFIX
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types
from koku.cache import invalidate_view_cache_for_tenant_and_cache_key
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from koku.cache import invalidate_view_cache_for_tenant_and_source_types
from koku.cache import KokuCacheError
from koku.cache import OPENSHIFT_ALL_CACHE_PREFIX
from koku.cache import OPENSHIFT_AWS_CACHE_PREFIX
from koku.cache import OPENSHIFT_AZURE_CACHE_PREFIX
from koku.cache import OPENSHIFT_CACHE_PREFIX


LOG = logging.getLogger(__name__)

CACHE_PREFIXES = (
    AWS_CACHE_PREFIX,
    AZURE_CACHE_PREFIX,
    OPENSHIFT_CACHE_PREFIX,
    OPENSHIFT_AWS_CACHE_PREFIX,
    OPENSHIFT_AZURE_CACHE_PREFIX,
    OPENSHIFT_ALL_CACHE_PREFIX,
)


class KokuCacheTest(IamTestCase):
    """Test the cache functionality."""

    def setUp(self):
        """Set up cache tests."""
        super().setUp()

        self.cache = caches["default"]
        self.cache_key_prefix = random.choice(CACHE_PREFIXES)

    def tearDown(self):
        """Tear down the test."""
        super().tearDown()
        self.cache.clear()

    def test_invalidate_view_cache_for_tenant_and_cache_key(self):
        """Test that specific cache data is deleted."""
        key_to_clear = f"{self.schema_name}:{self.cache_key_prefix}"
        remaining_key = f"keeper:{self.cache_key_prefix}"
        cache_data = {key_to_clear: "value", remaining_key: "value"}
        self.cache.set_many(cache_data)

        self.assertIsNotNone(self.cache.get(key_to_clear))
        self.assertIsNotNone(self.cache.get(remaining_key))

        invalidate_view_cache_for_tenant_and_cache_key(self.schema_name, self.cache_key_prefix)

        self.assertIsNone(self.cache.get(key_to_clear))
        self.assertIsNotNone(self.cache.get(remaining_key))

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}})
    def test_invalidate_view_cache_for_tenant_and_cache_key_dummy_cache(self):
        """Test that using DummyCache logs correctly."""
        with self.assertLogs(logger="koku.cache", level="INFO"):
            invalidate_view_cache_for_tenant_and_cache_key(self.schema_name, self.cache_key_prefix)

    @override_settings(
        CACHES={
            "default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "worker_cache_table"}
        }
    )
    def test_invalidate_view_cache_for_tenant_and_cache_key_unsupported_backend(self):
        """Test that an unsupported cache backend raises an error."""
        with self.assertRaises(KokuCacheError):
            invalidate_view_cache_for_tenant_and_cache_key(self.schema_name, self.cache_key_prefix)

    def test_invalidate_view_cache_for_tenant_and_source_type(self):
        """Test that all views for a source type and tenant are invalidated."""
        aws_cache_key_prefixes = (AWS_CACHE_PREFIX, OPENSHIFT_AWS_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX)
        aws_cache_data = {}
        for prefix in aws_cache_key_prefixes:
            aws_cache_data.update({f"{self.schema_name}:{prefix}": "value"})
        self.cache.set_many(aws_cache_data)

        invalidate_view_cache_for_tenant_and_source_type(self.schema_name, "AWS")

        for key in aws_cache_data:
            self.assertIsNone(self.cache.get(key))

        openshift_cache_key_prefixes = (
            OPENSHIFT_CACHE_PREFIX,
            OPENSHIFT_AWS_CACHE_PREFIX,
            OPENSHIFT_AZURE_CACHE_PREFIX,
            OPENSHIFT_ALL_CACHE_PREFIX,
        )

        openshift_cache_data = {}
        for prefix in openshift_cache_key_prefixes:
            openshift_cache_data.update({f"{self.schema_name}:{prefix}": "value"})
        self.cache.set_many(openshift_cache_data)

        invalidate_view_cache_for_tenant_and_source_type(self.schema_name, "OCP")

        for key in openshift_cache_data:
            self.assertIsNone(self.cache.get(key))

        azure_cache_key_prefixes = (AZURE_CACHE_PREFIX, OPENSHIFT_AZURE_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX)

        azure_cache_data = {}
        for prefix in azure_cache_key_prefixes:
            azure_cache_data.update({f"{self.schema_name}:{prefix}": "value"})
        self.cache.set_many(azure_cache_data)

        invalidate_view_cache_for_tenant_and_source_type(self.schema_name, "Azure")

        for key in azure_cache_data:
            self.assertIsNone(self.cache.get(key))

    def test_invalidate_view_cache_for_tenant_and_source_types(self):
        """Test that all views for a all source types and tenant are invalidated."""
        sources = {
            "openshift": {
                "source_type": Provider.PROVIDER_OCP,
                "cache_keys": (
                    OPENSHIFT_CACHE_PREFIX,
                    OPENSHIFT_AWS_CACHE_PREFIX,
                    OPENSHIFT_AZURE_CACHE_PREFIX,
                    OPENSHIFT_ALL_CACHE_PREFIX,
                ),
                "cache_data": {},
            },
            "aws": {
                "source_type": Provider.PROVIDER_AWS,
                "cache_keys": (AWS_CACHE_PREFIX, OPENSHIFT_AWS_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX),
                "cache_data": {},
            },
        }

        # initialize data
        for source in sources:
            cache_keys = sources[source]["cache_keys"]
            cache_data = sources[source]["cache_data"]

            for prefix in cache_keys:
                cache_data.update({f"{self.schema_name}:{prefix}": "value"})
            self.cache.set_many(cache_data)

        # clear data based on given sources
        source_types = []
        for source in sources:
            source_types.append(sources[source]["source_type"])

        invalidate_view_cache_for_tenant_and_source_types(self.schema_name, source_types)

        # test to make sure data is cleared
        for source in sources:
            cache_data = sources[source]["cache_data"]

            for key in cache_data:
                self.assertIsNone(self.cache.get(key))

        # test for log warning on invalid source type
        with self.assertLogs() as captured:
            result = "unable to invalidate cache, bogus is not a valid source type"
            source_types = ["bogus"]
            invalidate_view_cache_for_tenant_and_source_types(self.schema_name, source_types)
            self.assertEqual(len(captured.records), 1)
            self.assertEqual(captured.records[0].getMessage(), result)

    def test_invalidate_view_cache_for_tenant_and_all_source_type(self):
        """Test that all views for a all source types and tenant are invalidated."""
        sources = {
            "openshift": {
                "source_type": Provider.PROVIDER_OCP,
                "cache_keys": (
                    OPENSHIFT_CACHE_PREFIX,
                    OPENSHIFT_AWS_CACHE_PREFIX,
                    OPENSHIFT_AZURE_CACHE_PREFIX,
                    OPENSHIFT_ALL_CACHE_PREFIX,
                ),
                "cache_data": {},
            },
            "aws": {
                "source_type": Provider.PROVIDER_AWS,
                "cache_keys": (AWS_CACHE_PREFIX, OPENSHIFT_AWS_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX),
                "cache_data": {},
            },
            "azure": {
                "source_type": Provider.PROVIDER_AZURE,
                "cache_keys": (AZURE_CACHE_PREFIX, OPENSHIFT_AZURE_CACHE_PREFIX, OPENSHIFT_ALL_CACHE_PREFIX),
                "cache_data": {},
            },
        }

        # initialize data
        for source in sources:
            cache_keys = sources[source]["cache_keys"]
            cache_data = sources[source]["cache_data"]

            for prefix in cache_keys:
                cache_data.update({f"{self.schema_name}:{prefix}": "value"})
            self.cache.set_many(cache_data)

        # clear all cached data
        invalidate_view_cache_for_tenant_and_all_source_types(self.schema_name)

        # test to make sure data is cleared
        for source in sources:
            cache_data = sources[source]["cache_data"]

            for key in cache_data:
                self.assertIsNone(self.cache.get(key))
