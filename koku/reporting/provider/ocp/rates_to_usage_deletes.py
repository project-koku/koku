#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Explicit deletes of rates_to_usage rows whose source or report period is being deleted.

rates_to_usage has no database FK to its report period or source (migration 0356): a cascade
from those parents ran inside the parent delete, over every partition, and made pipeline
inserts racing a provider delete fail. Callers delete the rows here, before the parents, in
the current tenant schema. Both statements use the (source_uuid, report_period_id, ...) index.
"""
import logging

from django.db import connection

from api.common import log_json
from koku.database import fast_table_exists

LOG = logging.getLogger(__name__)

RTU_TABLE = "rates_to_usage"


def delete_rates_to_usage_for_source(source_uuid):
    """Delete every rates_to_usage row of one source. Returns the number of rows deleted."""
    if not fast_table_exists(RTU_TABLE):
        return 0
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {RTU_TABLE} WHERE source_uuid = %s::uuid", [str(source_uuid)])
        deleted = cursor.rowcount
    LOG.info(log_json(msg="deleted rates_to_usage rows of source", source_uuid=str(source_uuid), deleted=deleted))
    return deleted


def delete_rates_to_usage_for_report_periods(report_periods):
    """Delete the rates_to_usage rows of the given OCP report periods. Returns the number of rows deleted."""
    pairs = [(str(period.provider_id), period.id) for period in report_periods]
    if not pairs or not fast_table_exists(RTU_TABLE):
        return 0
    source_uuids, report_period_ids = zip(*pairs)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            DELETE FROM {RTU_TABLE} AS r
            USING unnest(%s::uuid[], %s::bigint[]) AS p(source_uuid, report_period_id)
            WHERE r.source_uuid = p.source_uuid
              AND r.report_period_id = p.report_period_id
            """,
            [list(source_uuids), list(report_period_ids)],
        )
        deleted = cursor.rowcount
    LOG.info(
        log_json(
            msg="deleted rates_to_usage rows of report periods",
            report_periods=list(report_period_ids),
            deleted=deleted,
        )
    )
    return deleted


def delete_rates_to_usage_for_source_report_period_ids(pairs):
    """Delete the rows of the given (source_uuid, report_period_id) pairs. Returns the number of rows deleted."""
    pairs = [(str(source_uuid), int(report_period_id)) for source_uuid, report_period_id in pairs]
    if not pairs or not fast_table_exists(RTU_TABLE):
        return 0
    source_uuids, report_period_ids = zip(*pairs)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            DELETE FROM {RTU_TABLE} AS r
            USING unnest(%s::uuid[], %s::bigint[]) AS p(source_uuid, report_period_id)
            WHERE r.source_uuid = p.source_uuid
              AND r.report_period_id = p.report_period_id
            """,
            [list(source_uuids), list(report_period_ids)],
        )
        return cursor.rowcount


def delete_rates_to_usage_for_rates_and_cost_models(rate_ids=(), cost_model_ids=()):
    """Delete the rows of the given rates and cost models, in every month. Returns the number of rows deleted.

    Uses the ratestousage_rate_id_idx / ratestousage_cost_model_id_idx indexes.
    """
    rate_ids = [str(rate_id) for rate_id in rate_ids]
    cost_model_ids = [str(cost_model_id) for cost_model_id in cost_model_ids]
    if not (rate_ids or cost_model_ids) or not fast_table_exists(RTU_TABLE):
        return 0
    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {RTU_TABLE} WHERE rate_id = ANY(%s::uuid[]) OR cost_model_id = ANY(%s::uuid[])",
            [rate_ids, cost_model_ids],
        )
        return cursor.rowcount


def _distinct_values(column):
    """Distinct non-null values of an indexed rates_to_usage column, by a loose index scan.

    Each step of the recursive query is one index probe ("the next value after the last"), so
    the cost grows with the number of distinct values, not with the number of rows.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH RECURSIVE v AS (
                (SELECT {column} AS value FROM {RTU_TABLE} WHERE {column} IS NOT NULL ORDER BY {column} LIMIT 1)
                UNION ALL
                SELECT n.value FROM v
                CROSS JOIN LATERAL (
                    SELECT r.{column} AS value FROM {RTU_TABLE} AS r
                    WHERE r.{column} > v.value ORDER BY r.{column} LIMIT 1
                ) AS n
            )
            SELECT value FROM v
            """
        )
        return [row[0] for row in cursor.fetchall()]


def _distinct_source_report_periods():
    """Distinct (source_uuid, report_period_id) pairs, by a loose scan of ratestousage_src_rp_mct_idx."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH RECURSIVE v AS (
                (SELECT source_uuid, report_period_id FROM {RTU_TABLE}
                 ORDER BY source_uuid, report_period_id LIMIT 1)
                UNION ALL
                SELECT n.source_uuid, n.report_period_id FROM v
                CROSS JOIN LATERAL (
                    SELECT r.source_uuid, r.report_period_id FROM {RTU_TABLE} AS r
                    WHERE (r.source_uuid, r.report_period_id) > (v.source_uuid, v.report_period_id)
                    ORDER BY r.source_uuid, r.report_period_id LIMIT 1
                ) AS n
            )
            SELECT source_uuid, report_period_id FROM v
            """
        )
        return cursor.fetchall()


def sweep_orphaned_rates_to_usage():
    """Delete rates_to_usage rows whose source, report period, rate or cost model no longer exists.

    rates_to_usage has no database FKs to its parents (migrations 0355, 0356). Their deletes remove
    the rows explicitly, but a pipeline run racing such a delete can still insert rows for a parent
    that is gone; this sweep bounds how long those survive. Runs in the current tenant schema.
    Returns the number of rows deleted per kind of parent.
    """
    deleted = {"sources": 0, "report_periods": 0, "rates_and_cost_models": 0}
    if not fast_table_exists(RTU_TABLE):
        return deleted
    # Imported here: the API models import this module's delete helpers.
    from api.provider.models import Provider
    from cost_models.models import CostModel
    from cost_models.models import Rate
    from reporting.provider.ocp.models import OCPUsageReportPeriod

    pairs = _distinct_source_report_periods()
    referenced_sources = {str(source_uuid) for source_uuid, _ in pairs}
    live_sources = {
        str(uuid) for uuid in Provider.objects.filter(uuid__in=referenced_sources).values_list("uuid", flat=True)
    }
    for source_uuid in sorted(referenced_sources - live_sources):
        deleted["sources"] += delete_rates_to_usage_for_source(source_uuid)

    live_pairs = [
        (str(source_uuid), period_id) for source_uuid, period_id in pairs if str(source_uuid) in live_sources
    ]
    live_periods = set(
        OCPUsageReportPeriod.objects.filter(id__in={period_id for _, period_id in live_pairs}).values_list(
            "id", flat=True
        )
    )
    orphan_pairs = [(source_uuid, period_id) for source_uuid, period_id in live_pairs if period_id not in live_periods]
    deleted["report_periods"] = delete_rates_to_usage_for_source_report_period_ids(orphan_pairs)

    rate_ids = {str(value) for value in _distinct_values("rate_id")}
    cost_model_ids = {str(value) for value in _distinct_values("cost_model_id")}
    orphan_rates = rate_ids - {
        str(uuid) for uuid in Rate.objects.filter(uuid__in=rate_ids).values_list("uuid", flat=True)
    }
    orphan_cost_models = cost_model_ids - {
        str(uuid) for uuid in CostModel.objects.filter(uuid__in=cost_model_ids).values_list("uuid", flat=True)
    }
    deleted["rates_and_cost_models"] = delete_rates_to_usage_for_rates_and_cost_models(
        sorted(orphan_rates), sorted(orphan_cost_models)
    )

    if any(deleted.values()):
        LOG.info(log_json(msg="swept orphaned rates_to_usage rows", deleted=deleted))
    return deleted
