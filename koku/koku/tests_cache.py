#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test view caching functions."""
import logging
import random

from django.core.cache import caches
from django.test.utils import override_settings

from api.iam.test.iam_test_case import IamTestCase
from koku.cache import AWS_CACHE_PREFIX
from koku.cache import AZURE_CACHE_PREFIX
from koku.cache import invalidate_view_cache_for_tenant_and_cache_key
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
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
