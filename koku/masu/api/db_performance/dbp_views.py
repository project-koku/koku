#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import os

from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from jinja2 import Template as JinjaTemplate
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny

from .db_performance import DBPerformanceStats
from koku.configurator import CONFIGURATOR


LOG = logging.getLogger(__name__)


MY_PATH = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(MY_PATH, "templates")
GENERIC_HTML_TMPL = JinjaTemplate(open(os.path.join(TEMPLATE_PATH, "gen_table.html"), "rt").read())


def render_template(page_header, fields, data):
    return GENERIC_HTML_TMPL.render(page_header=page_header, fields=fields, data=data)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def lockinfo(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = dbp.get_lock_info()

    page_header = "Lock Information"
    return HttpResponse(render_template(page_header, tuple(data[0]) if data else (), data))


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def stat_statements(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = dbp.get_statement_stats()

    page_header = "Statement Statistics"
    return HttpResponse(render_template(page_header, tuple(data[0]) if data else (), data))


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def stat_activity(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = dbp.get_activity()

    page_header = "Connection Activity"
    return HttpResponse(render_template(page_header, tuple(data[0]) if data else (), data))


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def dbsettings(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = dbp.get_pg_settings()

    page_header = "Database Settings"
    return HttpResponse(render_template(page_header, tuple(data[0]) if data else (), data))


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def pg_engine_version(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(request.user, CONFIGURATOR) as dbp:
        data = [{"postgresql_version": ".".join(str(v) for v in dbp.get_pg_engine_version())}]

    page_header = "PostgreSQL Engine Version"
    return HttpResponse(render_template(page_header, tuple(data[0]) if data else (), data))
