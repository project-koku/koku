#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Shared diagnostics and timeout guardrails for tag-mapping UPDATEs."""
import logging
import time
from contextlib import contextmanager

from django.conf import settings
from django.db import connection
from django.db import transaction

from api.common import log_json
from masu.processor import is_feature_flag_enabled_by_schema
from masu.processor import OCP_TAG_MAPPING_DIAGNOSTICS_FLAG
from masu.processor import OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG

LOG = logging.getLogger(__name__)


def run_tag_mapping_update(
    accessor, table_name, sql, sql_params, label, flag_checker=is_feature_flag_enabled_by_schema, logger=LOG
):
    """Run a tag-mapping UPDATE with optional plan logging and statement timeout."""
    diagnostics = flag_checker(accessor.schema, OCP_TAG_MAPPING_DIAGNOSTICS_FLAG, dev_fallback=True)
    timeout = flag_checker(accessor.schema, OCP_TAG_MAPPING_STATEMENT_TIMEOUT_FLAG, dev_fallback=True)
    if diagnostics:
        log_tag_mapping_plan(accessor, sql, sql_params, label, logger=logger)
    if timeout:
        with tag_mapping_statement_timeout(accessor.schema, logger=logger) as effective_timeout_ms:
            started = time.monotonic()
            try:
                accessor._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, redact_query_on_error=True)
            except Exception as exc:
                logger.error(
                    log_json(
                        msg=f"{label} tag-mapping UPDATE failed",
                        schema=accessor.schema,
                        start_date=str(sql_params["start_date"]),
                        end_date=str(sql_params["end_date"]),
                        report_period_ids=sql_params.get("report_period_ids", sql_params.get("report_period_id")),
                        configured_timeout_ms=settings.OCP_TAG_MAPPING_STATEMENT_TIMEOUT_MS,
                        effective_timeout_ms=effective_timeout_ms,
                        elapsed_seconds=time.monotonic() - started,
                        error_type=type(exc).__name__,
                        postgres_error_type=getattr(getattr(exc, "db_exception_type", None), "__name__", None),
                        pgcode=getattr(exc, "pgcode", None),
                        backend_pid=getattr(exc, "db_backend_pid", None),
                    )
                )
                raise
    elif diagnostics:
        accessor._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, redact_query_on_error=True)
    else:
        accessor._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)


def log_tag_mapping_plan(accessor, sql, sql_params, label, logger=LOG):
    """Log estimated plan shape without expressions that can contain parameter values."""
    try:
        prepared_sql, bind_params = accessor.prepare_query(sql, sql_params)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.db.set_schema(accessor.schema)
            cursor.execute("SELECT pg_backend_pid()")
            backend_pid = cursor.fetchone()[0]
            cursor.execute(f"EXPLAIN (FORMAT JSON) {prepared_sql}", params=bind_params)
            plan = cursor.fetchone()[0][0]["Plan"]

        nodes = []
        pending = [plan]
        while pending and len(nodes) < 32:
            node = pending.pop()
            nodes.append({key: node[key] for key in ("Node Type", "Plan Rows", "Total Cost") if key in node})
            pending.extend(reversed(node.get("Plans", [])))
        logger.info(
            log_json(
                msg=f"{label} tag-mapping planned EXPLAIN estimates",
                backend_pid=backend_pid,
                schema=accessor.schema,
                start_date=str(sql_params["start_date"]),
                end_date=str(sql_params["end_date"]),
                report_period_ids=sql_params.get("report_period_ids", sql_params.get("report_period_id")),
                plan_nodes=nodes,
                plan_truncated=bool(pending),
            )
        )
    except Exception as exc:
        logger.warning(
            log_json(msg=f"{label} tag-mapping EXPLAIN failed", schema=accessor.schema, error_type=type(exc).__name__)
        )


@contextmanager
def tag_mapping_statement_timeout(schema, logger=LOG):
    """Cap one tag-mapping UPDATE and restore the pooled connection setting."""
    configured_ms = settings.OCP_TAG_MAPPING_STATEMENT_TIMEOUT_MS
    if not 0 < configured_ms <= 2_147_483_647:
        raise ValueError("OCP_TAG_MAPPING_STATEMENT_TIMEOUT_MS must be between 1 and 2147483647")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('statement_timeout'), setting::bigint "
            "FROM pg_settings WHERE name = 'statement_timeout'"
        )
        previous_timeout, previous_ms = cursor.fetchone()
        effective_ms = min(previous_ms, configured_ms) if previous_ms else configured_ms
        changed = effective_ms != previous_ms
        if changed:
            cursor.execute("SELECT set_config('statement_timeout', %s, false)", [str(effective_ms)])
    update_error = None
    try:
        yield effective_ms
    except Exception as exc:
        update_error = exc
        raise
    finally:
        if changed:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('statement_timeout', %s, false)", [previous_timeout])
            except Exception:
                logger.error(log_json(msg="Could not restore tag-mapping statement timeout", schema=schema))
                connection.close()
                if update_error is None:
                    raise
