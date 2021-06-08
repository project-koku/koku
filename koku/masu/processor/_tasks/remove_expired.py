#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Remove expired data asynchronous tasks."""
import logging

from masu.processor.expired_data_remover import ExpiredDataRemover

LOG = logging.getLogger(__name__)


def _remove_expired_data(schema_name, provider, simulate, provider_uuid=None, line_items_only=False):
    """
    Task to remove expired data.

    Args:
        schema_name (String) db schema name
        provider    (String) provider type
        simulate    (Boolean) Simulate report data removal

    Returns:
        None

    """
    log_statement = (
        f"Remove expired data:\n"
        f" schema_name: {schema_name}\n"
        f" provider: {provider}\n"
        f" simulate: {simulate}\n"
        f" line_items_only: {line_items_only}\n"
    )
    LOG.info(log_statement)

    remover = ExpiredDataRemover(schema_name, provider)
    removed_data = remover.remove(simulate=simulate, provider_uuid=provider_uuid, line_items_only=line_items_only)
    if removed_data:
        status_msg = "Expired Data" if simulate else "Removed Data"
        result_msg = f"{status_msg}:\n {str(removed_data)}"
        LOG.info(result_msg)
