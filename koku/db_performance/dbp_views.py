#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

from django.http import HTTPResponse
from django.views.decorators.cache import never_cache
from jinja2 import Environment as JinjaEnv
from jinja2 import PackageLoader as JinjaLoader
from jinja2 import select_autoescape as jinja_autoescape
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny

from .db_performance import DBPerformanceStats
from koku.configurator import CONFIGURATOR

# from rest_framework.decorators import renderer_classes
# from rest_framework.settings import api_settings

LOG = logging.getLogger(__name__)


JENV = JinjaEnv(loader=JinjaLoader("dp_performance"), autoescape=jinja_autoescape())


def render_template(page_header, fields, data):
    tmpl = JENV.get_template("gen_table.html")
    return tmpl.render(page_header=page_header, fields=fields, data=data)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
# @renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def lockinfo(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = dbp.get_lock_info()

    page_header = "Lock Information"
    return HTTPResponse(render_template(page_header, tuple(data[0]) if data else (), data))


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
# @renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def stat_statements(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = dbp.get_statement_stats()

    page_header = "Statement Statistics"
    return HTTPResponse(render_template(page_header, tuple(data[0]) if data else (), data))


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
# @renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def stat_activity(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = dbp.get_activity()

    page_header = "Connection Activity"
    return HTTPResponse(render_template(page_header, tuple(data[0]) if data else (), data))


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
# @renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def dbsettings(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = dbp.get_settings()

    page_header = "Database Settings"
    return HTTPResponse(render_template(page_header, tuple(data[0]) if data else (), data))
