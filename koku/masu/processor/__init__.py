#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu Processor."""
import logging
from uuid import UUID

from django.conf import settings
from rest_framework.serializers import ValidationError

from api.common import log_json
from koku.feature_flags import fallback_development_true
from koku.feature_flags import UNLEASH_CLIENT
from masu.external import GZIP_COMPRESSED
from masu.external import UNCOMPRESSED
from masu.util.common import convert_account

LOG = logging.getLogger(__name__)

ALLOWED_COMPRESSIONS = (UNCOMPRESSED, GZIP_COMPRESSED)


def is_cost_6356_enabled():
    return UNLEASH_CLIENT.is_enabled(
        "cost-management.backend.cost-6356-vm-cost-model-metrics", fallback_function=fallback_development_true
    )


def is_feature_unattributed_storage_enabled_azure(account):
    """Should unattributed storage feature be enabled."""
    unleash_flag = "cost-management.backend.unattributed_storage"
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled(unleash_flag, context, fallback_development_true)


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


def is_customer_large(account):  # pragma: no cover
    """Flag the customer as large."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.large-customer", context)


def is_customer_penalty(account):  # pragma: no cover
    """Flag the customer as penalised."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.penalty-customer", context)


def is_rate_limit_customer_large(account):  # pragma: no cover
    """Flag the customer as large and to be rate limited."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.large-customer.rate-limit", context)


def is_validation_enabled(account):  # pragma: no cover
    """Flag if customer is enabled to run validation."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.enable_data_validation", context)


def is_managed_ocp_cloud_summary_enabled(account, provider_type):
    context = {"provider_type": provider_type}
    provider_flag = "cost-management.backend.feature-cost-5129-provider-type"
    if UNLEASH_CLIENT.is_enabled(provider_flag, context, fallback_development_true):
        account = convert_account(account)
        context = {"schema": account}
        summary_flag = "cost-management.backend.feature-cost-5129-ocp-cloud-summary"
        result = UNLEASH_CLIENT.is_enabled(summary_flag, context, fallback_development_true)
        LOG.info(log_json(msg=f"managed table summary enabled: {result}", schema=account, provider_type=provider_type))
        return result
    return False


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


def check_group_by_limit(account, group_by_length):
    """
    Checks to see if the customer has exceeded the group by limit.

    Raises a ValidationError if they have exceeded or returns false
    """
    limit = 2  # default
    if group_by_length <= limit:
        return
    account = convert_account(account)
    context = {"schema": account}
    if UNLEASH_CLIENT.is_enabled("cost-management.backend.override_customer_group_by_limit", context):
        limit = settings.MAX_GROUP_BY
        if group_by_length <= limit:
            return
    raise ValidationError({"group_by": (f"Cost Management supports a max of {limit} group_by options.")})


def is_feature_unattributed_storage_enabled_aws(account):
    """Should unattributed storage feature be enabled."""
    unleash_flag = "cost-management.backend.unattributed_storage.aws"
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled(unleash_flag, context, fallback_development_true)


def is_feature_cost_4403_ec2_compute_cost_enabled(account):  # pragma: no cover
    """Should EC2 individual VM compute cost be enabled."""
    unleash_flag = "cost-management.backend.feature-4403-enable-ec2-compute-processing"
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled(unleash_flag, context, fallback_development_true)


def is_feature_cost_20_openshift_vms_enabled(account):  # pragma: no cover
    """Should Openshift vms cost be enabled."""
    unleash_flag = "cost-management.backend.feature_cost_20_openshift_vms"
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled(unleash_flag, context, fallback_development_true)


def is_customer_cost_model_large(account):  # pragma: no cover
    """Flag the customer as having a large amount of data for cost model updates."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.large-customer-cost-model", context)


def is_tag_processing_disabled(account):  # pragma: no cover
    """Flag the customer as tag processing disabled."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.is_tag_processing_disabled", context)


def is_status_api_update_enabled(account):  # pragma: no cover
    """Flag to enable the new source status retrieval method."""
    account = convert_account(account)
    context = {"schema": account}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.is_status_api_update_enabled", context)
