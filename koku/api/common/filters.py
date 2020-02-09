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
"""Common filters for the views."""
from functools import reduce
from operator import and_

from django.db.models import Q
from django_filters import CharFilter
from django_filters.filters import BaseCSVFilter


class CharListFilter(BaseCSVFilter, CharFilter):
    """Add query filter capability to provide an anded list of filter values."""

    def filter(self, qs, value):
        """Filter to create a composite and filter of the value list."""
        if not value:
            return qs
        value_list = ",".join(value).split(",")
        queries = [Q(**{self.lookup_expr: val}) for val in value_list]
        return qs.filter(reduce(and_, queries))
