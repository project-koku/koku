#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu Processor."""
import logging
from uuid import UUID

from django.conf import settings

from api.common import log_json
from koku.feature_flags import fallback_development_true
from koku.feature_flags import UNLEASH_CLIENT
from masu.external import GZIP_COMPRESSED
from masu.external import UNCOMPRESSED
from masu.util.common import convert_account

LOG = logging.getLogger(__name__)

ALLOWED_COMPRESSIONS = (UNCOMPRESSED, GZIP_COMPRESSED)


def is_purge_trino_files_enabled(account):  # pragma: no cover
    """Helper to determine if account is enabled for deleting trino files."""
    account = convert_account(account)
    context = {"schema": account}
    LOG.debug(f"is_purge_trino_files_enabled context: {context}")
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.enable-purge-turnpike", context)


def is_cloud_source_processing_disabled(account):  # pragma: no cover
    """Disable processing for a cloud source."""
    account = convert_account(account)
    context = {"schema": account}
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-cloud-source-processing", context)
    if res:
        LOG.info(log_json(msg="processing disabled", context=context))

    return res


def is_summary_processing_disabled(account):  # pragma: no cover
    """Disable summary processing."""
    account = convert_account(account)
    context = {"schema": account}
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-summary-processing", context)
    if res:
        LOG.info(log_json(msg="summary processing disabled", context=context))

    return res


def is_ocp_on_cloud_summary_disabled(account):  # pragma: no cover
    """Disable OCP on Cloud summary."""
    account = convert_account(account)
    context = {"schema": account}
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-ocp-on-cloud-summary", context)
    if res:
        LOG.info(log_json(msg="OCP-on-Cloud summary processing disabled", context=context))

    return res


def is_gcp_resource_matching_disabled(account):  # pragma: no cover
    """Disable GCP resource matching for OCP on GCP."""
    account = convert_account(account)
    context = {"schema": account}
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-gcp-resource-matching", context)
    if res:
        LOG.info(log_json(msg="GCP resource matching is disabled", context=context))

    return res


def is_customer_large(account):  # pragma: no cover
    """Flag the customer as large."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.large-customer", context)


def is_rate_limit_customer_large(account):  # pragma: no cover
    """Flag the customer as large and to be rate limited."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.large-customer.rate-limit", context)


def is_ocp_savings_plan_cost_enabled(account):  # pragma: no cover
    """Enable the use of savings plan cost for OCP on AWS -> OCP."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled(
        "cost-management.backend.enable-ocp-savings-plan-cost", context, fallback_development_true
    )


def is_ocp_amortized_monthly_cost_enabled(account):  # pragma: no cover
    """Enable the use of savings plan cost for OCP on AWS -> OCP."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.enable-ocp-amortized-monthly-cost", context)


def is_source_disabled(source_uuid):  # pragma: no cover
    """
    Disable source processing

    params:
        source_uuid: unique identifer of source or provider
    """
    if isinstance(source_uuid, UUID):
        source_uuid = str(source_uuid)
    context = {"source_uuid": source_uuid}
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-source", context)
    if res:
        LOG.info(log_json(msg="processing disabled for source", context=context))
    return res


def is_ingress_rate_limiting_disabled():  # pragma: no cover
    """Disable ingress rate limiting"""
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-ingress-rate-limit")
    if res:
        LOG.info(log_json(msg="ingress rate limiting disabled"))
    return res


def get_customer_group_by_limit(account: str) -> int:  # pragma: no cover
    """Get the group_by limit for an account."""
    limit = 2
    account = convert_account(account)
    context = {"schema": account}
    if UNLEASH_CLIENT.is_enabled("cost-management.backend.override_customer_group_by_limit", context):
        limit = settings.MAX_GROUP_BY

    return limit


def check_ingress_columns(account):  # pragma: no cover
    """Should check ingress columns."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.check-ingress-columns", context)


def is_feature_cost_3592_tag_mapping_enabled(account):
    """Should tag mapping be enabled."""
    unleash_flag = "cost-management.backend.feature-cost-3592-tag-mapping"
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled(unleash_flag, context, fallback_development_true)


def is_feature_cost_3083_all_labels_enabled(account):
    """Should all labels column be enabled."""
    unleash_flag = "cost-management.backend.feature-cost-3083-all-labels"
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled(unleash_flag, context, fallback_development_true)


def is_feature_cost_4403_ec2_compute_cost_enabled(account):  # pragma: no cover
    """Should EC2 individual VM compute cost be enabled."""
    unleash_flag = "cost-management.backend.feature-4403-enable-ec2-compute-processing"
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled(unleash_flag, context, fallback_development_true)
