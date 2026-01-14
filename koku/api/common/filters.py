#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common filters for the views."""
from functools import reduce
from operator import and_

from django.db.models import Q
from django_filters import CharFilter
from django_filters.filters import BaseCSVFilter
from rest_framework.fields import CharField
from rest_framework.filters import SearchFilter


class CharListFilter(BaseCSVFilter, CharFilter):
    """Add query filter capability to provide an anded list of filter values."""

    def filter(self, qs, value):
        """Filter to create a composite and filter of the value list."""
        if not value:
            return qs
        value_list = ",".join(value).split(",")
        queries = [Q(**{self.lookup_expr: val}) for val in value_list]
        return qs.filter(reduce(and_, queries))


class SearchFilterResourceTypes(SearchFilter):
    """
    A search filter that treats the entire query as a single literal token.

    Unlike the default SearchFilter, this prevents the query from being split
    by spaces or commas, ensuring that multi-word resources (e.g., 'US East'
    or 'Red Hat') are matched exactly as typed rather than as separate keywords.

    This implementation leverages standard DRF CharField validation for security
    and input sanitization but bypasses the default 'search_smart_split' logic
    to preserve the query as a monolithic term.

    Note: If multi-term search (searching for several independent items at once)
    is required in the future, this can be updated to split strictly on commas
    while still preserving internal spaces.
    """

    def get_search_terms(self, request):
        value = request.query_params.get(self.search_param, "")
        field = CharField(trim_whitespace=False, allow_blank=True)
        cleaned_value = field.run_validation(value)

        return [cleaned_value] if cleaned_value else []
