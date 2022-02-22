#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""HCS Processor"""
import logging

from koku.feature_flags import UNLEASH_CLIENT
from masu.external import GZIP_COMPRESSED
from masu.external import UNCOMPRESSED

LOG = logging.getLogger(__name__)

ALLOWED_COMPRESSIONS = (UNCOMPRESSED, GZIP_COMPRESSED)


def enable_HCS_processing(source_uuid, source_type, account):  # noqa
    """Helper to determine if source is enabled for HCS."""
    if account and not account.startswith("acct"):
        account = f"acct{account}"

    context = {"schema": account, "source-type": source_type, "source-uuid": source_uuid}
    LOG.info(f"enable_hcs_processing context: {context}")
    return bool(UNLEASH_CLIENT.is_enabled("hcs-data-processor", context))
