#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for ISO currency helper functions."""
from django.test import override_settings
from django.test import SimpleTestCase

from api.currency.currencies import get_active_iso_currency_codes
from api.currency.currencies import is_active_iso_currency
from api.currency.currencies import is_valid_iso_currency


class ActiveIsoCurrencyHelpersTest(SimpleTestCase):
    """Tests for active-tender currency helpers."""

    def test_get_active_iso_currency_codes_excludes_xxx_and_frf(self):
        """Active tender set excludes XXX/FRF; full registry validation unchanged."""
        active_codes = get_active_iso_currency_codes()
        self.assertNotIn("XXX", active_codes)
        self.assertNotIn("FRF", active_codes)
        self.assertIn("USD", active_codes)
        self.assertFalse(is_active_iso_currency("XXX"))
        self.assertFalse(is_active_iso_currency("FRF"))
        self.assertTrue(is_active_iso_currency("USD"))
        self.assertTrue(is_valid_iso_currency("XXX"))

    @override_settings(CURRENCY_CATALOG_DENYLIST=frozenset({"KPW"}))
    def test_catalog_denylist_excludes_codes_from_active_set(self):
        """Denylisted tender codes are omitted from enablement helpers."""
        self.assertNotIn("KPW", get_active_iso_currency_codes())
        self.assertFalse(is_active_iso_currency("KPW"))
        self.assertTrue(is_valid_iso_currency("KPW"))
        self.assertIn("USD", get_active_iso_currency_codes())

    @override_settings(CURRENCY_CATALOG_DENYLIST=frozenset({"kpw", " chf "}))
    def test_catalog_denylist_normalizes_case_and_whitespace(self):
        """Denylist entries are matched case-insensitively after stripping."""
        self.assertFalse(is_active_iso_currency("KPW"))
        self.assertFalse(is_active_iso_currency("CHF"))
