#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Unit tests for ISO currency helper functions."""
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
