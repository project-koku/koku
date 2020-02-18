#
# Copyright 2018 Red Hat, Inc.
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
