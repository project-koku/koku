#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import logging
import os
import threading
from decimal import Decimal
from urllib.parse import urlencode

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from jinja2 import Template as JinjaTemplate
from psycopg2 import ProgrammingError
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from sqlparse import format as format_sql

from .db_performance import DBPerformanceStats
from koku.configurator import CONFIGURATOR


LOG = logging.getLogger(__name__)


MY_PATH = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(MY_PATH, "templates")

DBNAME_LOCK = threading.Lock()
APPLICATION_DBNAME = CONFIGURATOR.get_database_name()
ALL_DATABASES = []

# CANCEL_URL = 0
# TERMINATE_URL = 1


def get_database_list(dbps):
    with DBNAME_LOCK:
        if not ALL_DATABASES:
            ALL_DATABASES.append(APPLICATION_DBNAME)
            for rec in dbps.get_databases():
                if rec["datname"] != APPLICATION_DBNAME:
                    ALL_DATABASES.append(rec["datname"])

    return ALL_DATABASES


def get_limit_offset(request):
    try:
        limit = int(request.query_params.get("limit", "100"))
    except (TypeError, ValueError):
        limit = 100

    try:
        offset = int(request.query_params.get("offset"))
    except (TypeError, ValueError):
        offset = None

    return limit, offset


def get_selected_db(request):
    return request.query_params.get("dbname", CONFIGURATOR.get_database_name())


def get_parameter_list(request, param_name, default=None, sep=","):
    qp = request.query_params

    if param_name not in qp:
        return default

    param_val = qp.getlist(param_name)
    if len(param_val) == 1:
        param_val = param_val[0].split(sep)

    return param_val


def get_parameter_bool(request, param_name, default=None):
    if default is not None:
        default = bool(default)

    qp = request.query_params

    if param_name not in qp:
        return default

    param_val = qp.get(param_name, default)
    if isinstance(param_val, str):
        param_val = param_val.lower() in ("1", "y", "yes", "t", "true", "on")
    else:
        param_val = bool(param_val)

    return param_val


def get_menu(curr_url_name):
    menu_values = (
        ("db_version", "DB Engine Version"),
        ("db_settings", "DB Engine Settings"),
        ("conn_activity", "Connection Activity"),
        ("stmt_stats", "Statement Statistics"),
        ("lock_info", "Lock Information"),
        ("schema_sizes", "Schema Sizes"),
        ("explain_query", "Explain Query"),
    )
    menu_elements = ['<ul id="menu-list" class="menu unselectable">']
    for url_name, content_name in menu_values:
        if url_name == curr_url_name:
            element = f'<li class="current unselectable"><a class="unselectable">{content_name}</a></li>'
        else:
            element = (
                f'<li class="unselectable"><a class=unselectable href="{reverse(url_name)}">{content_name}</a></li>'
            )
        menu_elements.append(element)
    menu_elements.append("</ul>")

    return os.linesep.join(menu_elements)


def render_template(
    url_name,
    page_header,
    fields,
    data,
    targets=(),
    template="gen_table.html",
    action_urls=[],
    db_select=None,
    pagination=None,
):
    menu = get_menu(url_name)
    tmpl = JinjaTemplate(open(os.path.join(TEMPLATE_PATH, template)).read())
    return tmpl.render(
        db_performance_menu=menu,
        page_header=page_header,
        fields=fields,
        data=data,
        targets=targets,
        action_urls=action_urls,
        db_select=db_select,
        pagination=pagination,
    )


def set_null_display(rec, null_display_val=""):
    for col, val in rec.items():
        if val is None:
            rec[col] = null_display_val
    return rec


def get_identity_username(request):
    # This is a placeholder for now. This should resolve a username once actions are enabled.
    return "koku-user"


def make_db_options(databases, selected_db, request, target):
    jsnippet = """onchange="select_db(this)" """
    params = request.query_params.dict()
    path = reverse(target)
    buff = [f'<select name="dbname" {jsnippet}>']
    for db in databases:
        params["dbname"] = db
        url = f"{path}?{urlencode(params)}"
        sel = "selected" if db == selected_db else ""
        buff.append(f'    <option value="{url}" {sel}>{db}</option>')
    buff.append("</select>")
    return os.linesep.join(buff)


def make_pagination(limit, offset, data, request, target):
    offset = offset or 0
    diff = abs(limit - offset)
    links = []
    if offset <= 0:
        links.append("<span>Prev</span>")
    else:
        _prev = request.query_params.dict()
        _prev["limit"] = limit - diff
        _prev["offset"] = offset - diff
        url = f"{reverse(target)}?{urlencode(_prev)}"
        links.append(f"""<a href="{url}">&lt;&lt; Prev</a>""")
    if len(data) >= diff:
        _next = request.query_params.dict()
        _next["limit"] = limit + diff
        _next["offset"] = offset + diff
        url = f"{reverse(target)}?{urlencode(_next)}"
        links.append(f"""<a href="{url}">Next &gt;&gt;</a>""")
    else:
        links.append("<span>Next</span>")

    return "<span> | </span>".join(links)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def db_performance_redirect(request):
    return redirect("db_version")


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def lockinfo(request):
    """Get any blocked and blocking process data"""

    limit, offset = get_limit_offset(request)
    selected_db = get_selected_db(request)
    data = None
    databases = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        databases = get_database_list(dbp)
        data = dbp.get_lock_info(selected_db, limit=limit, offset=offset)

    pagination = make_pagination(limit, offset, data, request, "lock_info")
    if not data:
        data = [{"Result": "No blocking locks"}]

    targets = []
    if "blocking_pid" in data[0]:
        targets.append("blocking_pid")
    if "blocked_pid" in data[0]:
        targets.append("blocked_pid")

    # action_urls = [reverse("db_cancel_connection")]
    # if request.query_params.get("terminate") == "enable":
    #     LOG.info("Enabling the pg_stat_activity terminate action template.")
    #     template = "t_action_table.html"
    #     action_urls.append(reverse("db_terminate_connection"))
    # elif request.query_params.get("cancel") == "enable":
    #     template = "action_table.html"
    # else:
    #     template = "gen_table.html"

    template = "t_action_table.html"

    if targets:
        for rec in data:
            set_null_display(rec)
            rec["_attrs"] = {
                "blocked_statement": 'class="pre monospace"',
                "blckng_proc_curr_stmt": 'class="pre monospace"',
                "blocking_pid": 'class="sans"',
                "blocked_pid": 'class="sans"',
            }
            activity_url = f'{reverse("conn_activity")}?pid={rec["blocking_pid"]}&pid={rec["blocked_pid"]}'
            for t in targets:
                rec[f"_raw_{t}"] = rec[t]
            if template != "gen_table.html":
                rec["blocking_pid"] = (
                    f'<a href="{activity_url}" title="Click this link to see the '
                    + f'current activity for pids {rec["_raw_blocking_pid"]}, '
                    + f'{rec["_raw_blocked_pid"]}">{rec["_raw_blocking_pid"]}</a>'
                )
                rec["blocked_pid"] = (
                    f'<a href="{activity_url}" title="Click this link to see the '
                    + f'current activity for pids {rec["_raw_blocked_pid"]}, '
                    + f'{rec["_raw_blocking_pid"]}">{rec["_raw_blocked_pid"]}</a>'
                )
            rec["blocked_statement"] = format_sql(
                rec["blocked_statement"], reindent=True, indent_realigned=True, keyword_case="upper"
            )
            rec["blckng_proc_curr_stmt"] = format_sql(
                rec["blckng_proc_curr_stmt"], reindent=True, indent_realigned=True, keyword_case="upper"
            )

    page_header = "Lock Information"
    db_options = make_db_options(databases, selected_db, request, "lock_info")
    return HttpResponse(
        render_template(
            "lock_info",
            page_header,
            tuple(f for f in data[0] if not f.startswith("_")) if data else (),
            data,
            targets=targets,
            template=template,
            db_select=db_options,
            pagination=pagination,
            # action_urls=action_urls,
        )
    )


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def stat_statements(request):
    """Get any blocked and blocking process data"""

    data = None
    query_bad_threshold = Decimal("5000")
    query_warn_threshold = Decimal("2500")
    limit, offset = get_limit_offset(request)
    selected_db = get_selected_db(request)

    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        databases = get_database_list(dbp)
        data = dbp.get_statement_stats(selected_db, limit=limit, offset=offset)

    pagination = make_pagination(limit, offset, data, request, "stmt_stats")
    action_urls = []
    if data and "mean_exec_time" in data[0]:
        for rec in data:
            set_null_display(rec)
            rec["_attrs"] = {"query": 'class="pre monospace"'}
            rec["query"] = format_sql(rec["query"], reindent=True, indent_realigned=True, keyword_case="upper")
            for col in ("min_exec_time", "mean_exec_time", "max_exec_time"):
                attrs = ['class="sans"']
                if rec[col] > query_bad_threshold:
                    attrs.append('style="background-color: #d16969;"')
                elif rec[col] > query_warn_threshold:
                    attrs.append('style="background-color: #c7d169;"')
                else:
                    attrs.append('style="background-color: #69d172;"')
                rec["_attrs"][col] = " ".join(attrs)

        # action_urls.append(reverse("stat_statements_reset"))
    else:
        data = [{"Result": "No data matching the criteria"}]

    page_header = "Statement Statistics"
    db_options = make_db_options(databases, selected_db, request, "stmt_stats")
    return HttpResponse(
        render_template(
            "stmt_stats",
            page_header,
            tuple(f for f in data[0] if not f.startswith("_")) if data else (),
            data,
            template="stats_table.html",
            action_urls=action_urls,
            db_select=db_options,
            pagination=pagination,
        )
    )


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def stat_activity(request):
    """Get any blocked and blocking process data"""

    # action_urls = [reverse("db_cancel_connection")]
    # if request.query_params.get("terminate") == "enable":
    #     LOG.info("Enabling the pg_stat_activity terminate action template.")
    #     template = "t_action_table.html"
    #     action_urls.append(reverse("db_terminate_connection"))
    # elif request.query_params.get("cancel") == "enable":
    #     template = "action_table.html"
    # else:
    #     template = "gen_table.html"

    template = "t_action_table.html"
    states = get_parameter_list(request, "state", default=[])
    pids = get_parameter_list(request, "pid", default=[])
    limit, offset = get_limit_offset(request)
    selected_db = get_selected_db(request)

    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        databases = get_database_list(dbp)
        data = dbp.get_activity(
            selected_db,
            pid=pids,
            state=states,
            limit=limit,
            offset=offset,
        )

    pagination = make_pagination(limit, offset, data, request, "conn_activity")
    if not data:
        data = [{"Response": "No data matching the criteria"}]
        targets = ()
    else:
        targets = ("backend_pid",)
        rec_attrs = {
            "query": 'class="pre monospace"',
            "state": 'class="monospace"',
            "backend_pid": 'class="sans"',
            "client_ip": 'class="sans"',
            "backend_start": 'class="sans"',
            "xact_start": 'class="sans"',
            "query_start": 'class="sans"',
            "state_change": 'class="sans"',
            "active_time": 'class="sans"',
            "wait_type_event": 'class="sans"',
        }
        for rec in data:
            set_null_display(rec)
            rec["_raw_backend_pid"] = rec["backend_pid"]
            rec["_attrs"] = rec_attrs
            rec["query"] = format_sql(rec["query"], reindent=True, indent_realigned=True, keyword_case="upper")

    fields = tuple(f for f in data[0] if not f.startswith("_")) if data else ()

    page_header = "Connection Activity"
    db_options = make_db_options(databases, selected_db, request, "conn_activity")
    return HttpResponse(
        render_template(
            "conn_activity",
            page_header,
            fields,
            data,
            targets=targets,
            template=template,
            db_select=db_options,
            pagination=pagination,
            # action_urls=action_urls,
        )
    )


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def dbsettings(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        data = dbp.get_pg_settings()

    for rec in data:
        set_null_display(rec)

        rec["_attrs"] = {
            "category": 'style="font-weight: bold;"',
            "name": 'class="monospace"',
            "unit": 'class="monospace"',
            "setting": 'class="monospace"',
            "boot_val": 'class="monospace"',
            "reset_val": 'class="monospace"',
            "pending_restart": 'class="monospace"',
        }

    page_header = "Database Settings"
    return HttpResponse(
        render_template(
            "db_settings", page_header, tuple(f for f in data[0] if not f.startswith("_")) if data else (), data
        )
    )


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def pg_engine_version(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        data = [{"postgresql_version": dbp.get_pg_engine_version()}]

    page_header = "PostgreSQL Engine Version"
    return HttpResponse(render_template("db_version", page_header, tuple(data[0]) if data else (), data))


@never_cache
@api_view(http_method_names=["POST", "GET"])
@permission_classes((AllowAny,))
def explain_query(request):
    """Get any blocked and blocking process data"""
    if request.method == "GET":
        page_header = f"""Explain Query Using Database: "{CONFIGURATOR.get_database_name()}" """
        return HttpResponse(
            render_template(
                "explain_query", page_header, (), (), template="explain.html", action_urls=[reverse("explain_query")]
            )
        )
    else:
        query_params = json.loads(request.body.decode("utf-8"))

        data = None
        with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
            try:
                data = dbp.explain_sql(query_params["sql_statement"])
            except ProgrammingError as e:
                data = {"query_plan": f"{type(e).__name__}: {str(e)}"}
            else:
                all_plans = []
                enumeration = len(data) > 1
                if enumeration:
                    all_plans.append(f"Detected {len(data)} queries:")

                for p_num, plan in enumerate(data):
                    header = f"QUERY PLAN {p_num + 1}{os.linesep}" if enumeration else f"QUERY PLAN{os.linesep}"
                    all_plans.append(f'{header}{plan["query_plan"]}')

                data = {"query_plan": (os.linesep * 3).join(all_plans)}

        return Response(data)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def schema_sizes(request):
    """Get any blocked and blocking process data"""

    limit, offset = get_limit_offset(request)
    top = int(request.query_params.get("top", "0"))
    if top > limit:
        top = limit
    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        data = dbp.get_schema_sizes(top=top, limit=limit, offset=offset)

    pagination = make_pagination(limit, offset, data, request, "schema_sizes")
    for rec in data:
        set_null_display(rec)

        rec["_attrs"] = {
            "schema_name": 'class="monospace"',
            "table_name": 'class="monospace"',
            "table_size_gb": 'class="sans"',
            "schema_size_gb": 'class="sans"',
        }

    table_header = "and Top {top} Table " if top else ""
    page_header = f'Schema {table_header}Sizes for Database "{APPLICATION_DBNAME}"'
    return HttpResponse(
        render_template(
            "schema_sizes",
            page_header,
            tuple(f for f in data[0] if not f.startswith("_")) if data else (),
            data,
            pagination=pagination,
        )
    )
