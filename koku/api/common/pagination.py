#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common pagination class."""
import logging

from django.http import JsonResponse
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param

from api import API_VERSION
from api.utils import DateHelper

PATH_INFO = "PATH_INFO"
LOG = logging.getLogger(__name__)


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
                LOG.warning(f'Unable to rewrite link as "{version}" was not found.')
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


class ForecastListPaginator(ListPaginator):
    """A paginator that applies a default limit based on days in month."""

    default_limit = DateHelper().this_month_end.day


class ReportPagination(StandardResultsSetPagination):
    """A specialty paginator for report data."""

    default_limit = 100

    def __init__(self):
        """Set the parameters."""
        self.others = None

    def get_count(self, queryset):
        """Determine a report data's count."""
        return len(queryset.get("data", []))

    def get_limit_parameter(self, request):
        """Get the limit parameter from request."""
        if request.query_params.get(self.limit_query_param) is not None:
            return int(request.query_params.get(self.limit_query_param))
        return None

    def paginate_queryset(self, queryset, request, view=None):
        """Override queryset pagination."""
        self.count = self.get_count(queryset)
        if self.get_limit_parameter(request) == 0:
            self.limit = 0
        else:
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

        if self.limit:
            query_data = queryset.get("data", [])[self.offset : self.offset + self.limit]  # noqa
        else:
            query_data = queryset.get("data", [])

        queryset["data"] = query_data

        return queryset

    def get_paginated_response(self, data):
        """Override pagination output."""
        paginated_data = data.pop("data", [])
        filter_limit = data.get("filter", {}).get("limit", 0)
        meta = {"count": self.count}
        if self.others:
            others = 0
            if self.others > filter_limit:
                others = self.others - filter_limit
            meta["others"] = others
        response = {
            "meta": meta,
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


class OrgUnitPagination(ReportPagination):
    """A paginator of org units."""

    def __init__(self, params):
        """Set the parameters."""
        self.limit = params.get("limit", 10)
        self.offset = params.get("offset", 0)
        self.count = 0
        self.others = None

    def paginate_queryset(self, dataset, request, view=None):
        """Override queryset pagination."""
        self.request = request
        org_objects = []
        org_data = dataset.get("data")
        for date in org_data:
            if date.get("org_entities"):
                for entry in date.get("org_entities"):
                    org_objects.append(entry["id"])
                date["org_entities"] = date["org_entities"][self.offset : self.offset + self.limit]  # noqa: E203
        org_objects = set(org_objects)
        self.count = len(org_objects)
        return dataset


class EmptyResultsSetPagination(StandardResultsSetPagination):
    """A paginator for an empty response."""

    def __init__(self, data_set, request):
        """Initialize the paginator."""
        self.data_set = data_set
        self.request = request
        self.count = len(data_set)
        self.limit = 0
        self.offset = 0

    def get_paginated_response(self):
        """Override pagination output."""
        return JsonResponse(
            {
                "meta": {"count": self.count},
                "links": {
                    "first": self.get_first_link(),
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                    "last": self.get_last_link(),
                },
                "data": self.data_set,
            }
        )


class CustomMetaPagination(ListPaginator):
    """A specialty paginator that allows for passing of meta data."""

    def __init__(self, data, request, others=None):
        """Set the parameters."""
        self.data_set = data
        self.others = others
        self.request = request
        self.count = len(data)
        self.limit = self.get_limit(self.request)
        self.offset = self.get_offset(self.request)

    def get_paginated_response(self):
        """Override pagination output."""
        meta = {"count": self.count}
        if self.others is not None:
            for key, value in self.others.items():
                meta[key] = value
        response = {
            "meta": meta,
            "links": {
                "first": self.get_first_link(),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "last": self.get_last_link(),
            },
            "data": self.data_set,
        }
        return Response(response)
