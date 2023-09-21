#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Logic to deprecate a view."""
import logging
import typing as t
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from functools import wraps

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.utils import DateHelper

LOG = logging.getLogger(__name__)
HTTP_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S"

# Developer Note:
# In order to deprecate an endpoint you will need to add the
# deprecation_datetime & sunset_datetime to the view you are
# deprecating.

# Example:
# class SettingsView(APIView):
#     """
#     View to interact with settings for a customer.
#     """
#     deprecation_datetime = datetime(2023, 9, 22)
#     sunset_datetime = datetime(2023, 1, 10)
#     link = "https://github.com/project-koku/koku/pull/4670"

# Then import deprecate_view wrapper and it to the view in the
# urls.py

# Example:
# path("settings/", deprecate_view(SettingsView.as_view()), name="settings"),


@dataclass
class DeprecateEndpoint:
    viewclass: t.Callable
    deprecation_datetime: datetime = field(init=False)
    sunset_datetime: datetime = field(init=False)
    link: str = field(init=False)
    sunset_endpoint: bool = field(init=False)

    def _extract_data_from_class(self):
        """Checks that the view class has the correct attributes and format."""
        self.sunset_endpoint = False
        try:
            sunset_datetime = getattr(self.viewclass, "sunset_datetime")
            deprecation_datetime = getattr(self.viewclass, "deprecation_datetime")
            if deprecation_datetime < DateHelper(True).now:
                self.sunset_endpoint = True
            self.deprecation_datetime = deprecation_datetime.strftime(HTTP_DATE_FORMAT)
            self.sunset_datetime = sunset_datetime.strftime(HTTP_DATE_FORMAT)
            if hasattr(self.viewclass, "link"):
                self.link = getattr(self.viewclass, "link")
        except AttributeError:
            LOG.warning("Missing required attributes to deprecate endpoint.")

    def __post_init__(self):
        self._extract_data_from_class()

    def add_deprecation_header(self, response):
        """Adds deprecation to the response header."""
        # https://greenbytes.de/tech/webdav/draft-ietf-httpapi-deprecation-header-latest.html
        if self.deprecation_datetime:
            response["Deprecation"] = self.deprecation_datetime
        if self.sunset_datetime:
            response["Sunset"] = self.sunset_datetime
        if self.link:
            response["Link"] = self.link


@api_view(("GET",))
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def SunsetView(request, *args, **kwargs):
    return Response(status=status.HTTP_301_MOVED_PERMANENTLY)


def deprecate_view(viewfunc):
    @wraps(viewfunc)
    def _wrapped_view_func(request, *args, **kw):
        dataclass = DeprecateEndpoint(viewfunc.view_class)
        if dataclass.sunset_endpoint:
            return SunsetView(request, *args, **kw)
        response = viewfunc(request, *args, **kw)
        dataclass.add_deprecation_header(response)
        return response

    return _wrapped_view_func
