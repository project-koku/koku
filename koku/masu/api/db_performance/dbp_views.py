#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import logging
import os
from decimal import Decimal

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

DATABASE_RANKING = [CONFIGURATOR.get_database_name()]

# CANCEL_URL = 0
# TERMINATE_URL = 1


def get_menu(curr_url_name):
    menu_values = (
        ("db_version", "DB Engine Version"),
        ("db_settings", "DB Engine Settings"),
        ("conn_activity", "Connection Activity"),
        ("stmt_stats", "Statement Statistics"),
        ("lock_info", "Lock Information"),
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


def render_template(url_name, page_header, fields, data, targets=(), template="gen_table.html", action_urls=[]):
    menu = get_menu(url_name)
    tmpl = JinjaTemplate(open(os.path.join(TEMPLATE_PATH, template), "rt").read())
    return tmpl.render(
        db_performance_menu=menu,
        page_header=page_header,
        fields=fields,
        data=data,
        targets=targets,
        action_urls=action_urls,
    )


def set_null_display(rec, null_display_val=""):
    for col, val in rec.items():
        if val is None:
            rec[col] = null_display_val
    return rec


def get_identity_username(request):
    # This is a placeholder for now. This should resolve a username once actions are enabled.
    return "koku-user"


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

    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        data = dbp.get_lock_info()

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
            activity_url = f'{reverse("conn_activity")}?pids={rec["blocking_pid"]},{rec["blocked_pid"]}'
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
    return HttpResponse(
        render_template(
            "lock_info",
            page_header,
            tuple(f for f in data[0] if not f.startswith("_")) if data else (),
            data,
            targets=targets,
            template=template,
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

    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR, database_ranking=DATABASE_RANKING) as dbp:
        data = dbp.get_statement_stats()

    action_urls = []
    if "mean_exec_time" in data[0]:
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

    page_header = "Statement Statistics"
    return HttpResponse(
        render_template(
            "stmt_stats",
            page_header,
            tuple(f for f in data[0] if not f.startswith("_")) if data else (),
            data,
            template="stats_table.html",
            action_urls=action_urls,
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
    states = request.query_params.get("states", "")
    states = states.split(",") if states else []
    pids = request.query_params.get("pids", "")
    pids = [int(pid) for pid in pids.split(",")] if pids else []
    include_self = request.query_params.get("include_self", "false").lower() in ("1", "y", "yes", "t", "true", "on")

    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR, database_ranking=DATABASE_RANKING) as dbp:
        data = dbp.get_activity(pid=pids, state=states, include_self=include_self)

    fields = tuple(f for f in data[0] if not f.startswith("_")) if data else ()
    for rec in data:
        set_null_display(rec)
        rec["_raw_backend_pid"] = rec["backend_pid"]
        rec["_attrs"] = {
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
        rec["query"] = format_sql(rec["query"], reindent=True, indent_realigned=True, keyword_case="upper")

    page_header = "Connection Activity"
    return HttpResponse(
        render_template("conn_activity", page_header, fields, data, targets=("backend_pid",), template=template)
        # render_template(
        #     "conn_activity",
        #     page_header,
        #     fields,
        #     data,
        #     targets=("backend_pid",),
        #     template=template,
        #     action_urls=action_urls
        # )
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
        data = [{"postgresql_version": ".".join(str(v) for v in dbp.get_pg_engine_version())}]

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
