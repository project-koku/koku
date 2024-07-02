#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Remove expired data asynchronous tasks."""
import logging

from api.common import log_json
from masu.processor.expired_data_remover import ExpiredDataRemover

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

    context = {"schema": schema_name, "provider_type": provider, "provider_uuid": provider_uuid, "simulate": simulate}

    LOG.info(log_json(msg="Remove expired data", context=context))

    remover = ExpiredDataRemover(schema_name, provider)
    removed_data = remover.remove(simulate=simulate, provider_uuid=provider_uuid)
    if removed_data:
        status_msg = "Expired Data" if simulate else "Removed Data"
        LOG.info(log_json(msg=status_msg, removed_data=removed_data, context=context))
