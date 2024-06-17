#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Remove expired data asynchronous tasks."""
import logging

from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.expired_data_remover import ExpiredDataRemoverError

LOG = logging.getLogger(__name__)


def _remove_expired_data(schema_name, provider, simulate, provider_uuid=None):
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
    )
    LOG.info(log_statement)

    remover = ExpiredDataRemover(schema_name, provider)
    removed_data = remover.remove(simulate=simulate, provider_uuid=provider_uuid)
    if removed_data:
        status_msg = "Expired Data" if simulate else "Removed Data"
        result_msg = f"{status_msg}:\n {str(removed_data)}"
        LOG.info(result_msg)
    # We could extend the logic below here, or keep it as a separate celery task


def _remove_expired_trino_migrations(schema_name, provider_type, simulate, provider_uuid=None):
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
        f" provider_type: {provider_type}\n"
        f" simulate: {simulate}\n"
    )
    LOG.info(log_statement)

    try:
        remover = ExpiredDataRemover(schema_name, provider_type)
    except ExpiredDataRemoverError:
        return

    removed_trino_migrations = remover.remove_expired_trino_partitions(simulate=simulate, provider_uuid=provider_uuid)
    if removed_trino_migrations:
        status_msg = "Expired Partitions" if simulate else "Removed Partitions"
        result_msg = f"{status_msg}:\n {str(removed_trino_migrations)}"
        LOG.info(result_msg)
