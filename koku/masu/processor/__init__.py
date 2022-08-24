#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu Processor."""
import logging

from django.conf import settings

from koku.feature_flags import UNLEASH_CLIENT
from masu.external import GZIP_COMPRESSED
from masu.external import UNCOMPRESSED

LOG = logging.getLogger(__name__)

ALLOWED_COMPRESSIONS = (UNCOMPRESSED, GZIP_COMPRESSED)


def enable_trino_processing(source_uuid, source_type, account):  # noqa
    """Helper to determine if source is enabled for Trino."""
    if account and not account.startswith("acct") and not account.startswith("org"):
        account = f"acct{account}"

    context = {"schema": account, "source-type": source_type, "source-uuid": source_uuid}
    LOG.info(f"enable_trino_processing context: {context}")
    return bool(
        settings.ENABLE_PARQUET_PROCESSING
        or source_uuid in settings.ENABLE_TRINO_SOURCES
        or source_type in settings.ENABLE_TRINO_SOURCE_TYPE
        or account in settings.ENABLE_TRINO_ACCOUNTS
        or UNLEASH_CLIENT.is_enabled("cost-trino-processor", context)
    )


def enable_purge_trino_files(account):
    """Helper to determine if account is enabled for deleting trino files."""
    if account and not account.startswith("acct") and not account.startswith("org"):
        account = f"acct{account}"

    context = {"schema": account}
    LOG.info(f"enable_purge_trino_files context: {context}")
    return bool(UNLEASH_CLIENT.is_enabled("enable-purge-turnpike", context))


def disable_cloud_source_processing(account):
    if account and not account.startswith("acct") and not account.startswith("org"):
        account = f"acct{account}"

    context = {"schema": account}
    LOG.info(f"Processing UNLEASH check: {context}")
    res = bool(UNLEASH_CLIENT.is_enabled("disable_cloud_source_processing", context))
    LOG.info(f"    Processing {'disabled' if res else 'enabled'}")

    return res
