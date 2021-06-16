#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu Processor."""
import logging

from django.conf import settings

from masu.external import GZIP_COMPRESSED
from masu.external import UNCOMPRESSED

LOG = logging.getLogger(__name__)

ALLOWED_COMPRESSIONS = (UNCOMPRESSED, GZIP_COMPRESSED)


def enable_trino_processing(source_uuid, source_type, account):  # noqa
    """Helper to determine if source is enabled for Trino."""
    if account and not account.startswith("acct"):
        account = f"acct{account}"

    LOG.debug(f"enable_trino_processing({source_uuid}, {source_type}, {account})")
    if (
        settings.ENABLE_PARQUET_PROCESSING
        or source_uuid in settings.ENABLE_TRINO_SOURCES
        or source_type in settings.ENABLE_TRINO_SOURCE_TYPE
        or account in settings.ENABLE_TRINO_ACCOUNTS
    ):
        return True
    return False
