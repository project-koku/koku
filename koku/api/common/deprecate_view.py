#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Logic to deprecate a view."""
import logging
from dataclasses import dataclass
from dataclasses import field
from functools import wraps

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from api.utils import DateHelper

LOG = logging.getLogger(__name__)
HTTP_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S"


@dataclass
class DeprecateEndpoint:
    """
    In order to deprecate an endpoint you will need to add the
    deprecation_datetime & sunset_datetime to the view you are
    deprecating.

    Example:
    class SettingsView(APIView):
        deprecation_datetime = datetime(2023, 9, 22)
        sunset_datetime = datetime(2023, 1, 10)
        link = "https://github.com/project-koku/koku/pull/4670"

    Then import deprecate_view wrapper and add it to the view in the
    urls.py

    Example:
        path("settings/", deprecate_view(SettingsView.as_view()), name="settings"),
    """

    viewclass: APIView
    sunset_endpoint: bool = field(init=False, default=False)

    def update_response_headers(self, response):
        """Add sunset, deprecation, and link headers to the response if set on self.viewclass"""
        # https://greenbytes.de/tech/webdav/draft-ietf-httpapi-deprecation-header-latest.html
        if sunset_datetime := getattr(self.viewclass, "sunset_datetime", None):
            response["Sunset"] = sunset_datetime.strftime(HTTP_DATE_FORMAT)
            if sunset_datetime < DateHelper(True).now:
                self.sunset_endpoint = True
        if deprecation_datetime := getattr(self.viewclass, "deprecation_datetime", None):
            response["Deprecation"] = deprecation_datetime.strftime(HTTP_DATE_FORMAT)
        if link := getattr(self.viewclass, "link", None):
            response["Link"] = link


@api_view(("GET",))
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def SunsetView(request, *args, **kwargs):
    return Response(status=status.HTTP_301_MOVED_PERMANENTLY)


def deprecate_view(viewfunc):
    @wraps(viewfunc)
    def _wrapped_view_func(request, *args, **kw):
        deprecate = DeprecateEndpoint(viewfunc.view_class)
        response = viewfunc(request, *args, **kw)
        deprecate.update_response_headers(response)
        if deprecate.sunset_endpoint:
            return SunsetView(request, *args, **kw)
        return response

    return _wrapped_view_func
