#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""API views for CSV output."""
from rest_framework_csv.renderers import CSVRenderer


class PaginatedCSVRenderer(CSVRenderer):
    """
    A Paginated CSV Renderer.

    To be used with views that paginate data.
    """

    results_field = "data"

    def render(self, data, *args, **kwargs):
        """Render a paginated CSV."""
        if not isinstance(data, list):
            data = data.get(self.results_field, [])
        return super().render(data, *args, **kwargs)
