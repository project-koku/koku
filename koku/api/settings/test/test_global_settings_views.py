#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the GlobalSettingsView (data-retention endpoint)."""
import os
from unittest.mock import patch

from django.urls import clear_url_caches
from django.urls import path
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.settings.views import GlobalSettingsView
from masu.config import Config
from reporting.tenant_settings.models import TenantSettings


def _env_without_retain():
    """Return os.environ minus RETAIN_NUM_MONTHS (may be set by .env)."""
    return {k: v for k, v in os.environ.items() if k != "RETAIN_NUM_MONTHS"}


class _EnsureDataRetentionRoute:
    """Mixin that injects the data-retention URL when ONPREM is not set."""

    @classmethod
    def setUpClass(cls):
        from api import urls as api_urls

        cls._saved_patterns = api_urls.urlpatterns[:]
        names = {getattr(p, "name", None) for p in api_urls.urlpatterns}
        if "data-retention" not in names:
            for i, p in enumerate(api_urls.urlpatterns):
                if getattr(p, "name", None) == "get-account-setting":
                    api_urls.urlpatterns.insert(
                        i,
                        path(
                            "account-settings/data-retention/",
                            GlobalSettingsView.as_view(),
                            name="data-retention",
                        ),
                    )
                    break
            clear_url_caches()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        from api import urls as api_urls

        api_urls.urlpatterns[:] = cls._saved_patterns
        clear_url_caches()


class GlobalSettingsViewTest(_EnsureDataRetentionRoute, IamTestCase):
    """Tests for the data-retention GET/PUT endpoints."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = reverse("data-retention")
        self._env_patcher = patch.dict(os.environ, _env_without_retain(), clear=True)
        self._env_patcher.start()
        with schema_context(self.schema_name):
            TenantSettings.objects.all().delete()

    def tearDown(self):
        self._env_patcher.stop()
        super().tearDown()

    # ── GET ────────────────────────────────────────────────────

    def test_get_returns_default_when_no_row(self):
        """GET with no TenantSettings row returns the Config default."""
        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data_retention_months"], Config.MASU_RETAIN_NUM_MONTHS)
        self.assertFalse(response.data["env_override"])

    def test_get_returns_persisted_value(self):
        """GET returns the value from the DB when a row exists."""
        with schema_context(self.schema_name):
            TenantSettings.objects.create(data_retention_months=12)
        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data_retention_months"], 12)
        self.assertFalse(response.data["env_override"])

    def test_get_env_override_takes_precedence(self):
        """When RETAIN_NUM_MONTHS is set, GET returns env value + env_override=true."""
        with patch.dict("os.environ", {"RETAIN_NUM_MONTHS": "24"}):
            response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data_retention_months"], 24)
        self.assertTrue(response.data["env_override"])

    def test_get_returns_503_on_db_error(self):
        """GET returns 503 when the helper returns None (DB error)."""
        with patch("api.settings.views.get_data_retention_months", return_value=None):
            response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_get_is_side_effect_free(self):
        """GET must not create a TenantSettings row."""
        self.client.get(self.url, **self.headers)
        with schema_context(self.schema_name):
            self.assertEqual(TenantSettings.objects.count(), 0)

    # ── PUT ────────────────────────────────────────────────────

    def test_put_creates_row(self):
        """PUT creates a TenantSettings row when none exists."""
        data = {"data_retention_months": 6}
        response = self.client.put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        with schema_context(self.schema_name):
            row = TenantSettings.objects.first()
            self.assertIsNotNone(row)
            self.assertEqual(row.data_retention_months, 6)

    def test_put_updates_existing_row(self):
        """PUT updates an existing TenantSettings row."""
        with schema_context(self.schema_name):
            TenantSettings.objects.create(data_retention_months=6)
        data = {"data_retention_months": 12}
        response = self.client.put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        with schema_context(self.schema_name):
            row = TenantSettings.objects.first()
            self.assertEqual(row.data_retention_months, 12)

    def test_put_below_min_rejected(self):
        """PUT with value below min returns 400."""
        data = {"data_retention_months": 2}
        response = self.client.put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_above_max_rejected(self):
        """PUT with value above max returns 400."""
        data = {"data_retention_months": 121}
        response = self.client.put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_missing_field_rejected(self):
        """PUT without data_retention_months returns 400."""
        data = {}
        response = self.client.put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_non_integer_rejected(self):
        """PUT with a non-integer value returns 400."""
        data = {"data_retention_months": "abc"}
        response = self.client.put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_blocked_when_env_override(self):
        """PUT returns 403 when RETAIN_NUM_MONTHS env var is set."""
        with patch.dict("os.environ", {"RETAIN_NUM_MONTHS": "24"}):
            data = {"data_retention_months": 6}
            response = self.client.put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_single_row_invariant(self):
        """Multiple PUTs should not create multiple rows."""
        for months in (6, 12, 24):
            self.client.put(self.url, {"data_retention_months": months}, format="json", **self.headers)
        with schema_context(self.schema_name):
            self.assertEqual(TenantSettings.objects.count(), 1)
            self.assertEqual(TenantSettings.objects.first().data_retention_months, 24)


class GlobalSettingsViewRBACTest(_EnsureDataRetentionRoute, IamTestCase):
    """RBAC tests for the data-retention endpoint."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = reverse("data-retention")
        self._env_patcher = patch.dict(os.environ, _env_without_retain(), clear=True)
        self._env_patcher.start()
        with schema_context(self.schema_name):
            TenantSettings.objects.all().delete()

    def tearDown(self):
        self._env_patcher.stop()
        super().tearDown()

    no_access = {"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["*"]}}
    read = {"settings": {"read": ["*"]}}
    write = {"settings": {"write": ["*"]}}
    read_write = {"settings": {"read": ["*"], "write": ["*"]}}

    @RbacPermissions(no_access)
    def test_no_access_get(self):
        """GET without settings access returns 403."""
        response = APIClient().get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions(no_access)
    def test_no_access_put(self):
        """PUT without settings access returns 403."""
        data = {"data_retention_months": 6}
        response = APIClient().put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions(read)
    def test_read_access_get(self):
        """GET with read access returns 200."""
        response = APIClient().get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions(read)
    def test_read_access_put_rejected(self):
        """PUT with read-only access returns 403."""
        data = {"data_retention_months": 6}
        response = APIClient().put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions(write)
    def test_write_access_put(self):
        """PUT with write access returns 204."""
        data = {"data_retention_months": 6}
        response = APIClient().put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @RbacPermissions(write)
    def test_write_access_get_rejected(self):
        """GET with write-only access returns 403."""
        response = APIClient().get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions(read_write)
    def test_read_write_get(self):
        """GET with read+write access returns 200."""
        response = APIClient().get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions(read_write)
    def test_read_write_put(self):
        """PUT with read+write access returns 204."""
        data = {"data_retention_months": 6}
        response = APIClient().put(self.url, data, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
