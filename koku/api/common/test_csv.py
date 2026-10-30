#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for the CSV renderer formula-injection sanitization."""
from django.test import TestCase

from api.common.csv import _FORMULA_PREFIXES
from api.common.csv import _sanitize_csv_cell
from api.common.csv import _sanitize_csv_row
from api.common.csv import PaginatedCSVRenderer


class SanitizeCsvCellTests(TestCase):
    """Unit tests for _sanitize_csv_cell."""

    def test_formula_prefixes_are_escaped(self):
        """Cells starting with any formula prefix get a leading single-quote."""
        for prefix in _FORMULA_PREFIXES:
            value = f"{prefix}CMD|'/C calc'!A0"
            result = _sanitize_csv_cell(value)
            self.assertEqual(result[0], "'", f"Prefix {prefix!r} was not escaped; got {result!r}")
            self.assertIn(value, result)

    def test_safe_values_are_unchanged(self):
        """Cells that do not start with a formula prefix pass through unchanged."""
        for safe in ["hello", "123", " =formula", "abc=def", "", "normal text"]:
            self.assertEqual(_sanitize_csv_cell(safe), safe)

    def test_non_string_values_are_unchanged(self):
        """Non-string values (int, float, None) are returned as-is."""
        for value in [42, 3.14, None, True, ["list"]]:
            self.assertEqual(_sanitize_csv_cell(value), value)


class SanitizeCsvRowTests(TestCase):
    """Unit tests for _sanitize_csv_row."""

    def test_row_dict_values_are_sanitized(self):
        """All string values in a row dict are sanitized."""
        row = {"name": "=evil", "safe": "hello", "num": 99}
        result = _sanitize_csv_row(row)
        self.assertEqual(result["name"], "'=evil")
        self.assertEqual(result["safe"], "hello")
        self.assertEqual(result["num"], 99)

    def test_non_dict_row_is_unchanged(self):
        """Non-dict rows are returned as-is."""
        row = ["=evil", "safe"]
        self.assertEqual(_sanitize_csv_row(row), row)


class PaginatedCSVRendererTests(TestCase):
    """Integration tests for PaginatedCSVRenderer formula-injection sanitization."""

    def setUp(self):
        self.renderer = PaginatedCSVRenderer()

    def test_render_sanitizes_paginated_data(self):
        """render() prefixes formula cells in paginated data dict."""
        data = {"count": 1, "data": [{"amount": "=SUM(A1:A10)", "label": "safe"}]}
        # render() returns bytes/str CSV; we just need to verify no ValueError and the
        # sanitized value appears in the output.
        output = self.renderer.render(data, media_type="text/csv", renderer_context={})
        self.assertIn("'=SUM(A1:A10)", output.decode() if isinstance(output, bytes) else output)

    def test_render_sanitizes_list_data(self):
        """render() prefixes formula cells when data is a plain list."""
        data = [{"col": "+1-2"}]
        output = self.renderer.render(data, media_type="text/csv", renderer_context={})
        self.assertIn("'+1-2", output.decode() if isinstance(output, bytes) else output)

    def test_render_leaves_safe_values_intact(self):
        """render() does not alter cells that are already safe."""
        data = {"count": 1, "data": [{"label": "normal", "value": "100"}]}
        output = self.renderer.render(data, media_type="text/csv", renderer_context={})
        csv_text = output.decode() if isinstance(output, bytes) else output
        self.assertIn("normal", csv_text)
        self.assertIn("100", csv_text)
        self.assertNotIn("'normal", csv_text)
