#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for get_data_retention_months helper."""
import os
from unittest.mock import patch

from django_tenants.utils import schema_context

from api.settings.utils import get_data_retention_months
from masu.config import Config
from masu.test import MasuTestCase
from reporting.tenant_settings.models import TenantSettings


class GetDataRetentionMonthsTest(MasuTestCase):
    """Tests for the get_data_retention_months helper."""

    def setUp(self):
        """Remove RETAIN_NUM_MONTHS from env (may be set by .env) and clean DB."""
        super().setUp()
        self._env_patcher = patch.dict(
            os.environ,
            {k: v for k, v in os.environ.items() if k != "RETAIN_NUM_MONTHS"},
            clear=True,
        )
        self._env_patcher.start()
        with schema_context(self.schema):
            TenantSettings.objects.all().delete()

    def tearDown(self):
        self._env_patcher.stop()
        super().tearDown()

    # ── Priority chain ─────────────────────────────────────────

    def test_returns_config_default_when_no_row_no_env(self):
        """No env var + no DB row → Config.MASU_RETAIN_NUM_MONTHS."""
        result = get_data_retention_months(self.schema)
        self.assertEqual(result, Config.MASU_RETAIN_NUM_MONTHS)

    def test_returns_db_value_when_row_exists(self):
        """No env var + DB row → row value."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=18)
        result = get_data_retention_months(self.schema)
        self.assertEqual(result, 18)

    def test_env_var_takes_precedence_over_db(self):
        """Env var set + DB row → env var value."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=18)
        with patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "36"}):
            result = get_data_retention_months(self.schema)
        self.assertEqual(result, 36)

    def test_env_var_takes_precedence_over_default(self):
        """Env var set + no DB row → env var value."""
        with patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "10"}):
            result = get_data_retention_months(self.schema)
        self.assertEqual(result, 10)

    # ── R7: DB error handling ──────────────────────────────────

    def test_db_error_returns_none(self):
        """When the DB query raises, helper returns None (R7 safety)."""
        with patch("api.settings.utils.TenantSettings.objects") as mock_objects:
            mock_objects.first.side_effect = Exception("connection lost")
            result = get_data_retention_months(self.schema)
        self.assertIsNone(result)

    def test_db_error_does_not_raise(self):
        """DB errors are swallowed — no exception propagates."""
        with patch("api.settings.utils.TenantSettings.objects") as mock_objects:
            mock_objects.first.side_effect = RuntimeError("disk full")
            try:
                get_data_retention_months(self.schema)
            except Exception:
                self.fail("get_data_retention_months raised on DB error")

    def test_db_error_logged(self):
        """DB errors are logged at ERROR level."""
        with patch("api.settings.utils.TenantSettings.objects") as mock_objects:
            mock_objects.first.side_effect = Exception("boom")
            with self.assertLogs("api.settings.utils", level="ERROR") as cm:
                get_data_retention_months(self.schema)
        self.assertTrue(any("Failed to read tenant_settings" in msg for msg in cm.output))

    # ── Edge cases ─────────────────────────────────────────────

    def test_env_var_zero_returns_zero(self):
        """Env var set to '0' returns 0 (view layer validates bounds)."""
        with patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "0"}):
            result = get_data_retention_months(self.schema)
        self.assertEqual(result, 0)

    def test_returns_int_type(self):
        """Return value is always int (or None on error)."""
        result = get_data_retention_months(self.schema)
        self.assertIsInstance(result, int)
