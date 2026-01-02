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


class SingleTokenSearchFilter(SearchFilter):
    """
    A search filter that does not split search strings by spaces.
    Treats 'US East' as one search term instead of ['US', 'East'].
    """

    def get_search_terms(self, request):
        params = request.query_params.get(self.search_param, "")
        params = params.replace("\x00", "")  # substitute-character cleanup
        # We return a list containing the whole string if it exists
        return [params] if params else []
