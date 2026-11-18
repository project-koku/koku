#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""QueryFilterfor Reports."""
from collections import defaultdict
from collections import UserDict
from functools import total_ordering

from django.db.models import Q


@total_ordering
class QueryFilter(UserDict):
    """Dict-like object representing a single query filter."""

    SEP = "__"  # separator
    table = None
    field = None
    operation = None
    parameter = None
    composition_key = None

    def __init__(
        self,
        table=None,
        field=None,
        operation=None,
        parameter=None,
        composition_key=None,
        custom=None,
        logical_operator=None,
    ):
        """Constructor.

        Args:
            table (str) - The name of a DB table
            field (str) - The name of a DB field
            operation (str) - The name of a DB operation, e.g. 'in' or 'gte'
            parameter (object) - A valid query target, e.g. a list or datetime
            composition_key(str) - A key used for composing filters on different fields into an OR
            logical_operator (str) - 'and' or 'or'

        """
        super().__init__(table=table, field=field, operation=operation, parameter=parameter)
        self.table = table
        self.field = field
        self.operation = operation
        self.parameter = parameter
        self.composition_key = composition_key
        self.logical_operator = "or"
        if logical_operator:
            self.logical_operator = logical_operator
        if logical_operator == "exact":
            self.operation = "exact"

    def composed_query_string(self):
        """Return compiled query string."""
        fields = [entry for entry in [self.table, self.field, self.operation] if entry is not None]
        return self.SEP.join(fields)

    def compose_key(self):
        """Return compose key or composed_query_string."""
        key = self.composition_key
        if key is None:
            key = self.composed_query_string()
        return key

    def composed_Q(self):
        """Return a Q object formatted for Django's ORM."""
        if isinstance(self.parameter, Q):
            # This will allow us to add Qs directly to
            # the filter collection
            return self.parameter

        query_dict = {self.composed_query_string(): self.parameter}
        return Q(**query_dict)

    def from_string(self, query_string):
        """Parse a string representing a filter.

        Returns:
            QueryFilter instance.

        Args:
            query_string (str) A string representing a query filter.

        Example:
            QueryFilter().from_string('mytable__myfield__contains')

        """
        parts = query_string.split(self.SEP)
        if len(parts) == 3:
            self.table, self.field, self.operation = parts
        elif len(parts) == 2:
            self.table, self.operation = parts
        else:
            message = "Incorrect number of parts in query string. " + "Need at least two of [table, field, operation]."
            raise TypeError(message)
        return self

    def __eq__(self, other):
        """Exact comparison."""
        return self.data == other.data and self.logical_operator == other.logical_operator

    def __lt__(self, other):
        """Decide if self < other."""
        return str(self.data) < str(other.data)

    def __repr__(self):
        """Return string representation."""
        return str(self.composed_Q())


class QueryFilterCollection:
    """Object representing a set of filters for a query.

    This object behaves in list-like ways.
    """

    def __init__(self, filters=None):
        """Constructor.

        Args:
            filters (list) a list of QueryFilter instances.

        """
        if filters is None:
            self._filters = list()  # a list of QueryFilter objects
        else:
            if not isinstance(filters, list):
                raise TypeError("filters must be a list")

            if not all(isinstance(item, QueryFilter) for item in filters):
                raise TypeError("Filters list must contain QueryFilters.")

            self._filters = filters

    def add(self, query_filter=None, table=None, field=None, operation=None, parameter=None):
        """Add a query filter to the collection.

        QueryFilterCollection does try to maintain filter uniqueness. A new
        object will not be added to the collection if it already exists.

        Args:
            query_filter (QueryFilter) a QueryFilter object

            - or -

            table (str)  db table name
            field (str)  db field/row name
            operation (str) db operation
            parameter (object) query object

        """
        error_message = "query_filter can not be defined with other parameters"
        if query_filter and (table or field or operation or parameter):
            raise AttributeError(error_message)

        if query_filter and query_filter not in self:
            self._filters.append(query_filter)

        if table or field or operation or parameter:
            qf = QueryFilter(table=table, field=field, operation=operation, parameter=parameter)
            if qf not in self:
                self._filters.append(qf)

    def compose(self, logical_operator=None):
        """Compose filters into a dict for submitting to Django's ORM.

        Args:
            logical_operator (str): 'and' or 'or' -- how to combine the filters.

        """
        composed_query = Q()
        compose_dict = defaultdict(list)
        operator = "and"
        if logical_operator == "or":
            operator = "or"

        for filt in self._filters:
            filt_key = filt.compose_key()
            compose_dict[filt_key].append(filt)

        for filter_list in compose_dict.values():
            or_filter = Q()
            for filter_item in filter_list:
                if filter_item.logical_operator == "and":
                    or_filter &= filter_item.composed_Q()
                else:
                    or_filter |= filter_item.composed_Q()
            if operator == "or":
                composed_query |= or_filter
            else:
                composed_query &= or_filter
        return composed_query

    def __contains__(self, item):
        """Return a boolean about whether `item` is in the collection.

        This will do both an exact and a fuzzy match. Exact matches are
        preferred over fuzzy matches. However, if there is no exact match,
        __contains__ will return `True` if there is an object that contains all
        of the same properties as `item`, even if additional properties are
        set on the object in our collection. (See: `QueryFilterCollection.get()`)

        Args:
            item (QueryFilter or dict) object to search for.

        Returns:
            (bool) Whether a matching object was found.

        """
        if isinstance(item, QueryFilter):
            return item in self._filters
        if isinstance(item, dict) and self.get(item):
            return True
        return False

    def __eq__(self, other):
        """Exact comparison."""
        return sorted(self._filters) == sorted(other._filters)

    def __iter__(self):
        """Return an iterable of the collection."""
        return self._filters.__iter__()

    def __getitem__(self, key):
        """Return object identified by key.

        Args:
            key (int) the index of the QueryFilter to return.

        """
        return self._filters[key]

    def __repr__(self):
        """Return string representation."""
        out = f"{self.__class__}: "
        for filt in self._filters:
            out += filt.__repr__() + ", "
        return out

    def __len__(self):
        """Return the length of the collection."""
        return len(self._filters)

    def delete(self, query_filter=None, table=None, field=None, operation=None, parameter=None):
        """Delete a query filter from the collection.

        Args:
            query_filter (QueryFilter) a QueryFilter object

            - or -

            table (str)  db table name
            field (str)  db field/row name
            operation (str) db operation
            parameter (object) query object

        """
        error_message = "query_filter can not be defined with other parameters"
        if query_filter and (table or field or operation or parameter):
            raise AttributeError(error_message)

        if query_filter and query_filter in self:
            self._filters.remove(query_filter)

        if table or field or operation or parameter:
            qf = QueryFilter(table=table, field=field, operation=operation, parameter=parameter)
            if qf in self:
                self._filters.remove(qf)

    def get(self, search):
        """Retrieve the first matching filter in the collection.

        This is a "fuzzy" search. This method looks for an object that matches
        all key-value pairs of `search` with an object in the collection. The
        matched object may have additional properties set to a non-None value.

        Args:
            search (dict) A dictionary of filter parameters to search for.

        Example:
            These examples are in order of least-specific (most likely to have
            more than one result) to most-specific (most likely to have exactly
            one result).

            QueryFilterCollection.get({'operation': 'contains'})

            QueryFilterCollection.get({'table': 'mytable', 'operation': 'gte'})

            QueryFilterCollection.get({'table': 'mytable',
                                       'field': 'myfield',
                                       'operation': 'in'})

        """
        for idx, filt in enumerate(self._filters):
            filter_values = [filt.get(key) for key in search.keys() if filt.get(key)]
            search_values = [search.get(key) for key in search.keys() if search.get(key)]
            filter_values.sort()
            search_values.sort()
            if search_values == filter_values:
                return (idx, filt)
        return None
