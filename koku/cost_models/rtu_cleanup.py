#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Schedule removal of rates_to_usage rows after Rate or CostModel deletes.

rates_to_usage.rate_id and .cost_model_id have no database cascade (migration 0355):
deleting through a cascade made a rate edit scan every partition of a large table
inside the API request. Instead, the API schedules delete_rates_to_usage_rows in the
cost model worker once its transaction commits; a rolled-back delete schedules nothing.
"""
from django.db import connection
from django.db import transaction

from common.queues import CostModelQueue
from common.queues import get_customer_queue


def schedule_rates_to_usage_cleanup(rate_ids=(), cost_model_ids=()):
    """Schedule delete_rates_to_usage_rows for the current tenant after the transaction commits."""
    rate_ids = sorted({str(rate_id) for rate_id in rate_ids})
    cost_model_ids = sorted({str(cost_model_id) for cost_model_id in cost_model_ids})
    if not rate_ids and not cost_model_ids:
        return
    schema_name = connection.schema_name

    def _dispatch():
        from masu.processor.tasks import delete_rates_to_usage_rows

        delete_rates_to_usage_rows.apply_async(
            args=[schema_name],
            kwargs={"rate_ids": rate_ids, "cost_model_ids": cost_model_ids},
            queue=get_customer_queue(schema_name, CostModelQueue),
        )

    transaction.on_commit(_dispatch)
