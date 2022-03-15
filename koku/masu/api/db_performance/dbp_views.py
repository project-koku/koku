#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import os
from decimal import Decimal

from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from jinja2 import Template as JinjaTemplate
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from sqlparse import format as format_sql

from .db_performance import DBPerformanceStats
from koku.configurator import CONFIGURATOR


LOG = logging.getLogger(__name__)


MY_PATH = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(MY_PATH, "templates")

# CANCEL_URL = 0
# TERMINATE_URL = 1


def render_template(page_header, fields, data, targets=(), template="gen_table.html", action_urls=[]):
    tmpl = JinjaTemplate(open(os.path.join(TEMPLATE_PATH, template), "rt").read())
    return tmpl.render(page_header=page_header, fields=fields, data=data, targets=targets, action_urls=action_urls)


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
    query_warn_threshold = Decimal("4000")

    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
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

        # action_urls.append(reverse("clear_statement_statistics"))

    page_header = "Statement Statistics"
    return HttpResponse(
        render_template(
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
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
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
        render_template(page_header, fields, data, targets=("backend_pid",), template=template)
        # render_template(
        #     page_header, fields, data, targets=("backend_pid",), template=template, action_urls=action_urls
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
        render_template(page_header, tuple(f for f in data[0] if not f.startswith("_")) if data else (), data)
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
    return HttpResponse(render_template(page_header, tuple(data[0]) if data else (), data))
