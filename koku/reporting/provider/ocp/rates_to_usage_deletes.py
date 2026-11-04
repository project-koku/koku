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
