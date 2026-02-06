#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the cache invalidation endpoint."""
import logging
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import status

from koku.cache import CacheEnum
from masu.test import MasuTestCase

LOG = logging.getLogger(__name__)


@override_settings(ROOT_URLCONF="masu.urls")
@patch("koku.middleware.MASU", return_value=True)
class CacheInvalidationAPIViewTest(MasuTestCase):
    """Test Cases for the Cache Invalidation API."""

    def setUp(self):
        patcher = patch("masu.api.invalidate_cache.invalidate_cache_for_tenant_and_cache_key")
        self.mock_invalidate = patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def test_cache_invalidation_success(self, _):
        """Test the cache invalidation endpoint."""
        tests = [
            [
                {"schema_name": self.schema_name, "cache_name": "api"},
                {"schema_name": self.schema_name, "cache_name": "rbac"},
            ],
            [{"schema_name": self.schema_name, "cache_name": "api"}],
            [{"schema_name": self.schema_name, "cache_name": "rbac"}],
            {"schema_name": self.schema_name, "cache_name": "api"},
            {"schema_name": self.schema_name, "cache_name": "rbac"},
        ]
        url = reverse("invalidate_cache")
        for test in tests:
            with self.subTest(test=test):
                response = self.client.post(url, data=test, content_type="application/json")
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cache_invalidation_rbac_success(self, _):
        """Test the cache invalidation endpoint."""
        test_payload = {"schema_name": self.schema_name, "cache_name": "rbac"}
        url = reverse("invalidate_cache")
        response = self.client.post(url, data=test_payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.mock_invalidate.assert_called_once_with(
            self.schema_name.removeprefix("org"), cache_key_prefix=CacheEnum.rbac, cache_name=CacheEnum.rbac
        )

    def test_cache_invalidation_default_success(self, _):
        """Test the cache invalidation endpoint."""
        test_payload = {"schema_name": self.schema_name, "cache_name": "api"}
        url = reverse("invalidate_cache")
        response = self.client.post(url, data=test_payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.mock_invalidate.assert_called_once_with(
            self.schema_name, cache_key_prefix=None, cache_name=CacheEnum.api
        )

    def test_cache_invalidation_api_not_valid_type(self, _):
        """Test the cache invalidation endpoint."""
        tests = [
            [
                {"schema_name": self.schema_name, "cache_name": "api1"},
                {"schema_name": self.schema_name, "cache_name": "rbac1"},
            ],
            [{"schema_name": self.schema_name, "cache_name": "api1"}],
            [{"schema_name": self.schema_name, "cache_name": "rbac1"}],
            {"schema_name": self.schema_name, "cache_name": "api1"},
            {"schema_name": self.schema_name, "cache_name": "rbac1"},
        ]
        url = reverse("invalidate_cache")
        for test in tests:
            with self.subTest(test=test):
                response = self.client.post(url, data=test, content_type="application/json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.mock_invalidate.assert_not_called()

    def test_cache_invalidation_api_missing_params(self, _):
        tests = [
            [
                {"cache_name": "api1"},
                {"schema_name": self.schema_name},
            ],
            [{"cache_name": "api1"}],
            [{"schema_name": self.schema_name}],
            {"cache_name": "api1"},
            {"schema_name": self.schema_name},
        ]
        url = reverse("invalidate_cache")
        for test in tests:
            with self.subTest(test=test):
                response = self.client.post(url, data=test, content_type="application/json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.mock_invalidate.assert_not_called()

    def test_cache_invalidation_api_invalid_payloads(self, _):
        tests = [
            [
                "cache_name",
                "api1",
                {"schema_name": self.schema_name},
            ],
            "this is an invalid payload",
            {"hello", "invalid", "paylaods"},
        ]
        url = reverse("invalidate_cache")
        for test in tests:
            with self.subTest(test=test):
                response = self.client.post(url, data=test, content_type="application/json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.mock_invalidate.assert_not_called()
