#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common SUBS functions and vars."""
import logging

from api.common import log_json
from api.provider.models import Provider
from koku import settings
from koku.feature_flags import UNLEASH_CLIENT
from masu.util.common import convert_account


LOG = logging.getLogger(__name__)

SUBS_ACCEPTED_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    # Add additional accepted providers here
)


def enable_subs_processing(schema_name: str) -> bool:
    """Helper to determine if source is enabled for SUBS processing."""

    schema_name = convert_account(schema_name)
    context = {"schema_name": schema_name}
    LOG.info(log_json(msg="enable_subs_processing context", context=context))

    return bool(
        UNLEASH_CLIENT.is_enabled("cost-management.backend.subs-data-processing", context)
        or settings.ENABLE_SUBS_PROCESSING_DEBUG
    )
