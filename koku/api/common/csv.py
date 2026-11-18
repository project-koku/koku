#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""API views for CSV output."""
from rest_framework_csv.renderers import PaginatedCSVRenderer

# Characters that spreadsheet applications (Excel, LibreOffice Calc, Google Sheets)
# interpret as formula prefixes when they appear at the start of a cell value.
# Prefixing with a single-quote causes them to be treated as literal text (RFC 4180 safe).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_csv_cell(value):
    """Prefix cell values that begin with a spreadsheet formula character.

    Recurses into nested dicts and lists so that values at any depth are
    sanitized before the parent renderer flattens them into CSV columns.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    if isinstance(value, dict):
        return {k: _sanitize_csv_cell(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_csv_cell(item) for item in value]
    return value


def _sanitize_csv_row(row):
    """Sanitize all string values in a row dict against formula injection."""
    if isinstance(row, dict):
        return {k: _sanitize_csv_cell(v) for k, v in row.items()}
    return row


class PaginatedCSVRenderer(PaginatedCSVRenderer):
    """
    A Paginated CSV Renderer.

    To be used with views that paginate data.

    Sanitizes cell values to prevent CSV formula injection (CWE-1236).  Any cell
    whose string value starts with ``=``, ``+``, ``-``, ``@``, ``\\t``, or ``\\r``
    is prefixed with a single quote so spreadsheet applications treat it as text.
    """

    results_field = "data"

    def render(self, data, *args, **kwargs):
        """Render a paginated CSV with formula-injection prefix sanitization."""
        if isinstance(data, dict):
            rows = data.get(self.results_field)
            if isinstance(rows, list):
                data = {**data, self.results_field: [_sanitize_csv_row(row) for row in rows]}
        elif isinstance(data, list):
            data = [_sanitize_csv_row(row) for row in data]
        return super().render(data, *args, **kwargs)
