#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu Processor."""
import logging

from django.conf import settings

from koku.feature_flags import fallback_development_true
from koku.feature_flags import UNLEASH_CLIENT
from masu.external import GZIP_COMPRESSED
from masu.external import UNCOMPRESSED
from masu.util.common import convert_account


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
        or UNLEASH_CLIENT.is_enabled("cost-management.backend.cost-trino-processor", context)
    )


def enable_purge_trino_files(account):
    """Helper to determine if account is enabled for deleting trino files."""
    account = convert_account(account)

    context = {"schema": account}
    LOG.info(f"enable_purge_trino_files context: {context}")
    return bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.enable-purge-turnpike", context))


def disable_cloud_source_processing(account):
    """Disable processing for a cloud source."""
    account = convert_account(account)

    context = {"schema": account}
    LOG.info(f"Processing UNLEASH check: {context}")
    res = bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-cloud-source-processing", context))
    LOG.info(f"    Processing {'disabled' if res else 'enabled'} {account}")

    return res


def disable_summary_processing(account):
    """Disable summary processing."""
    account = convert_account(account)

    context = {"schema": account}
    LOG.info(f"Summary UNLEASH check: {context}")
    res = bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-summary-processing", context))
    LOG.info(f"    Summary {'disabled' if res else 'enabled'} {account}")

    return res


def disable_ocp_on_cloud_summary(account):
    """Disable OCP on Cloud summary."""
    account = convert_account(account)

    context = {"schema": account}
    LOG.info(f"OCP on Cloud Summary UNLEASH check: {context}")
    res = bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-ocp-on-cloud-summary", context))
    LOG.info(f"    OCP on Cloud Summary {'disabled' if res else 'enabled'} {account}")

    return res


def disable_gcp_resource_matching(account):
    """Disable GCP resource matching for OCP on GCP."""
    account = convert_account(account)

    context = {"schema": account}
    LOG.info(f"GCP resource matching UNLEASH check: {context}")
    res = bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-gcp-resource-matching", context))
    LOG.info(f"    GCP resource matching {'disabled' if res else 'enabled'} {account}")

    return res


def summarize_ocp_on_gcp_by_node(account):
    """This flag is a temporary stop gap to summarize large ocp on gcp customers by node."""
    account = convert_account(account)

    context = {"schema": account}
    LOG.info(f"OCP on GCP Summary by Node UNLEASH check: {context}")
    res = bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.summarize-ocp-on-gcp-by-node", context))
    LOG.info(f"    Summarize by Node for OCP on GCP {'enabled' if res else 'disabled'} {account}")

    return res


def is_large_customer(account):
    """Flag the customer as large."""
    account = convert_account(account)

    context = {"schema": account}
    res = bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.large-customer", context))

    return res


def enable_ocp_savings_plan_cost(account):
    """Enable the use of savings plan cost for OCP on AWS -> OCP."""
    account = convert_account(account)

    context = {"schema": account}
    res = bool(
        UNLEASH_CLIENT.is_enabled(
            "cost-management.backend.enable-ocp-savings-plan-cost", context, fallback_development_true
        )
    )

    return res


def enable_ocp_amortized_monthly_cost(account):
    """Enable the use of savings plan cost for OCP on AWS -> OCP."""
    account = convert_account(account)

    context = {"schema": account}
    res = bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.enable-ocp-amortized-monthly-cost", context))

    return res
