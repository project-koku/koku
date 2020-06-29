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
"""Common pagination class."""
import logging

from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param

from api import API_VERSION

PATH_INFO = "PATH_INFO"
logger = logging.getLogger(__name__)


class StandardResultsSetPagination(LimitOffsetPagination):
    """Create standard paginiation class with page size."""

    default_limit = 10
    max_limit = 1000

    @staticmethod
    def link_rewrite(request, link):
        """Rewrite the link based on the path header to only provide partial url."""
        url = link
        version = f"v{API_VERSION}/"
        if PATH_INFO in request.META:
            try:
                local_api_index = link.index(version)
                path = request.META.get(PATH_INFO)
                path_api_index = path.index(version)
                path_link = "{}{}"
                url = path_link.format(path[:path_api_index], link[local_api_index:])
            except ValueError:
                logger.warning(f'Unable to rewrite link as "{version}" was not found.')
        return url

    def get_first_link(self):
        """Create first link with partial url rewrite."""
        url = self.request.build_absolute_uri()
        offset = 0
        first_link = replace_query_param(url, self.offset_query_param, offset)
        first_link = replace_query_param(first_link, self.limit_query_param, self.limit)
        return StandardResultsSetPagination.link_rewrite(self.request, first_link)

    def get_next_link(self):
        """Create next link with partial url rewrite."""
        next_link = super().get_next_link()
        if next_link is None:
            return next_link
        return StandardResultsSetPagination.link_rewrite(self.request, next_link)

    def get_previous_link(self):
        """Create previous link with partial url rewrite."""
        previous_link = super().get_previous_link()
        if previous_link is None:
            return previous_link
        return StandardResultsSetPagination.link_rewrite(self.request, previous_link)

    def get_last_link(self):
        """Create last link with partial url rewrite."""
        url = self.request.build_absolute_uri()
        offset = self.count - self.limit if (self.count - self.limit) >= 0 else 0
        last_link = replace_query_param(url, self.offset_query_param, offset)
        last_link = replace_query_param(last_link, self.limit_query_param, self.limit)
        return StandardResultsSetPagination.link_rewrite(self.request, last_link)

    def get_paginated_response(self, data):
        """Override pagination output."""
        return Response(
            {
                "meta": {"count": self.count},
                "links": {
                    "first": self.get_first_link(),
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                    "last": self.get_last_link(),
                },
                "data": data,
            }
        )


class ListPaginator(StandardResultsSetPagination):
    """A paginator for a list."""

    def __init__(self, data_set, request):
        """Initialize the paginator."""
        self.data_set = data_set
        self.request = request
        self.count = len(data_set)
        self.limit = self.get_limit(self.request)
        self.offset = self.get_offset(self.request)

    @property
    def paginated_data_set(self):
        """Paginate the list."""
        if self.limit > len(self.data_set):
            self.limit = len(self.data_set)
        try:
            data = self.data_set[self.offset : self.offset + self.limit]  # noqa E203
        except IndexError:
            data = []
        return data

    @property
    def paginated_response(self):
        """Return the paginated repsonse."""
        return self.get_paginated_response(self.paginated_data_set)


class ReportPagination(StandardResultsSetPagination):
    """A specialty paginator for report data."""

    default_limit = 100

    def get_count(self, queryset):
        """Determine a report data's count."""
        return len(queryset.get("data", []))

    def paginate_queryset(self, queryset, request, view=None):
        """Override queryset pagination."""
        self.count = self.get_count(queryset)
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None
        self.offset = self.get_offset(request)
        self.request = request
        if self.count > self.limit and self.template is not None:
            self.display_page_controls = True

        if self.count == 0 or self.offset > self.count:
            queryset["data"] = []
            return queryset

        query_data = queryset.get("data", [])[self.offset : self.offset + self.limit]  # noqa
        queryset["data"] = query_data

        return queryset

    def get_paginated_response(self, data):
        """Override pagination output."""
        paginated_data = data.pop("data", [])
        response = {
            "meta": {"count": self.count},
            "links": {
                "first": self.get_first_link(),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "last": self.get_last_link(),
            },
            "data": paginated_data,
        }
        response["meta"].update(data)
        return Response(response)


class ReportRankedPagination(ReportPagination):
    """A specialty paginator for ranked report data."""

    default_limit = 5
    limit_query_param = "filter[limit]"
    offset_query_param = "filter[offset]"

    def get_count(self, queryset):
        """Determine a report data's count."""
        return self.count

    def paginate_queryset(self, queryset, request, view=None):
        """Override queryset pagination."""
        self.request = request
        self.limit = self.get_limit(request)
        self.offset = self.get_offset(request)

        return queryset
