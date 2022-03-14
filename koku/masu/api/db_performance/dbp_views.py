#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import base64
import json
import logging
import os
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from jinja2 import Template as JinjaTemplate
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

# CANCEL_URL = 0
# TERMINATE_URL = 1


def render_template(page_header, fields, data, targets=(), template="gen_table.html", action_urls=[], subheader=""):
    tmpl = JinjaTemplate(open(os.path.join(TEMPLATE_PATH, template), "rt").read())
    return tmpl.render(
        page_header=page_header,
        fields=fields,
        data=data,
        targets=targets,
        action_urls=action_urls,
        subheader=subheader,
    )


def set_null_display(rec, null_display_val=""):
    for col, val in rec.items():
        if val is None:
            rec[col] = null_display_val
    return rec


def get_identity(request):
    rh_ident_header = request.META.get("HTTP_X_RH_IDENTITY")
    if not rh_ident_header:
        return None

    identity = json.loads(base64.b64decode(rh_ident_header).decode("utf-8"))
    return identity


def validate_identity(identity_header):
    identity = identity_header.get("identity")
    entitlements = identity_header.get("entitlements")
    if not identity:
        LOG.warning("No identity found.")
        raise PermissionDenied("You must be logged into Red Hat.")

    if identity["type"] != "User" or not identity.get("user"):
        LOG.warning("Invalid identity found.")
        raise PermissionDenied("Invalid identity. Ensure that your are logged into Red Hat.")

    user = identity["user"]
    if not user.get("username") or not user.get("email"):
        LOG.warning("Malformed identity found.")
        raise PermissionDenied("Malformed identity. Ensure that your are logged into Red Hat.")

    if not entitlements.get("cost_management", {}).get("is_entitled", False):
        LOG.warning("Improper access detected.")
        raise PermissionDenied("You do not access to cost management. Please see an administrator to get access.")


def get_identity_username(request):
    ident = get_identity(request)
    validate_identity(ident)
    user = ident["identity"]["user"]
    return f"{user['username']} ({user['email']})"


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

    action_urls = [reverse("db_cancel_connection")]
    if request.query_params.get("terminate") == "enable":
        LOG.info("Enabling the pg_stat_activity terminate action template.")
        template = "t_action_table.html"
        action_urls.append(reverse("db_terminate_connection"))
    elif request.query_params.get("cancel") == "enable":
        template = "action_table.html"
    else:
        template = "gen_table.html"

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
                rec["blocking_pid"] = f'<a href="{activity_url}">{rec["blocking_pid"]}</a>'
                rec["blocked_pid"] = f'<a href="{activity_url}">{rec["blocked_pid"]}</a>'
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
            action_urls=action_urls,
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

    for rec in data:
        set_null_display(rec)
        rec["_attrs"] = {"query": 'class="pre monospace"'}
        rec["query"] = format_sql(rec["query"], reindent=True, indent_realigned=True, keyword_case="upper")
        for col in ("mean_exec_time", "max_exec_time"):
            attrs = ['class="sans"']
            if rec[col] > query_bad_threshold:
                attrs.append('style="background-color: #d16969;"')
            elif rec[col] > query_warn_threshold:
                attrs.append('style="background-color: #c7d169;"')
            else:
                attrs.append('style="background-color: #69d172;"')
            rec["_attrs"][col] = " ".join(attrs)

    action_urls = [reverse("clear_statement_statistics")]

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

    action_urls = [reverse("db_cancel_connection")]
    if request.query_params.get("terminate") == "enable":
        LOG.info("Enabling the pg_stat_activity terminate action template.")
        template = "t_action_table.html"
        action_urls.append(reverse("db_terminate_connection"))
    elif request.query_params.get("cancel") == "enable":
        template = "action_table.html"
    else:
        template = "gen_table.html"

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
        render_template(
            page_header, fields, data, targets=("backend_pid",), template=template, action_urls=action_urls
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


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def pg_cancel_backend(request):
    """Get any blocked and blocking process data"""

    backends = request.META.get("HTTP_PARAM_DB_CONNID")
    if backends:
        backends = [int(pid) for pid in backends.split("<")]

    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        data = dbp.cancel_backends(backends)

    return Response(data or {})


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def pg_terminate_backend(request):
    """Get any blocked and blocking process data"""

    backends = request.META.get("HTTP_PARAM_DB_CONNID")
    if backends:
        backends = [int(pid) for pid in backends.split("<")]

    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        data = dbp.terminate_backends(backends)

    return Response(data or {})


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
def clear_statement_statistics(request):
    """Get any blocked and blocking process data"""

    data = None
    with DBPerformanceStats(get_identity_username(request), CONFIGURATOR) as dbp:
        data = dbp.pg_stat_statements_reset()

    return Response(data)
