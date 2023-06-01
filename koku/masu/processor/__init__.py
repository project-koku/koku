#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Masu Processor."""
import logging

from koku.feature_flags import fallback_development_true
from koku.feature_flags import UNLEASH_CLIENT
from masu.external import GZIP_COMPRESSED
from masu.external import UNCOMPRESSED
from masu.util.common import convert_schema_name


LOG = logging.getLogger(__name__)

ALLOWED_COMPRESSIONS = (UNCOMPRESSED, GZIP_COMPRESSED)


def is_purge_trino_files_enabled(schema_name):
    """Helper to determine if schema_name is enabled for deleting trino files."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    LOG.info(f"enable_purge_trino_files context: {context}")
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.enable-purge-turnpike", context)


def is_cloud_source_processing_disabled(schema_name):
    """Disable processing for a cloud source."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    LOG.info(f"Processing UNLEASH check: {context}")
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-cloud-source-processing", context)
    LOG.info(f"    Processing {'disabled' if res else 'enabled'} {schema_name}")

    return res


def is_summary_processing_disabled(schema_name):
    """Disable summary processing."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    LOG.info(f"Summary UNLEASH check: {context}")
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-summary-processing", context)
    LOG.info(f"    Summary {'disabled' if res else 'enabled'} {schema_name}")

    return res


def is_ocp_on_cloud_summary_disabled(schema_name):
    """Disable OCP on Cloud summary."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    LOG.info(f"OCP on Cloud Summary UNLEASH check: {context}")
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-ocp-on-cloud-summary", context)
    LOG.info(f"    OCP on Cloud Summary {'disabled' if res else 'enabled'} {schema_name}")

    return res


def is_gcp_resource_matching_disabled(schema_name):
    """Disable GCP resource matching for OCP on GCP."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    LOG.info(f"GCP resource matching UNLEASH check: {context}")
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-gcp-resource-matching", context)
    LOG.info(f"    GCP resource matching {'disabled' if res else 'enabled'} {schema_name}")

    return res


def should_summarize_ocp_on_gcp_by_node(schema_name):
    """This flag is a temporary stop gap to summarize large ocp on gcp customers by node."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    LOG.info(f"OCP on GCP Summary by Node UNLEASH check: {context}")
    res = UNLEASH_CLIENT.is_enabled("cost-management.backend.summarize-ocp-on-gcp-by-node", context)
    LOG.info(f"    Summarize by Node for OCP on GCP {'enabled' if res else 'disabled'} {schema_name}")

    return res


def is_large_customer(schema_name):
    """Flag the customer as large."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.large-customer", context)


def is_ocp_savings_plan_cost_enabled(schema_name):
    """Enable the use of savings plan cost for OCP on AWS -> OCP."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    return UNLEASH_CLIENT.is_enabled(
        "cost-management.backend.enable-ocp-savings-plan-cost", context, fallback_development_true
    )


def is_ocp_amortized_monthly_cost_enabled(schema_name):
    """Enable the use of savings plan cost for OCP on AWS -> OCP."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    return UNLEASH_CLIENT.is_enabled("cost-management.backend.enable-ocp-amortized-monthly-cost", context)


def is_aws_category_settings_enabled(schema_name):
    """Enable aws category settings."""
    schema_name = convert_schema_name(schema_name)

    context = {"schema": schema_name}
    return UNLEASH_CLIENT.is_enabled(
        "cost-management.backend.enable_aws_category_settings", context, fallback_development_true
    )


def is_source_disabled(source_uuid):
    """
    Disable source processing

    params:
        source_uuid: unique identifer of source or provider
    """
    context = {"source_uuid": source_uuid}
    LOG.info(f"Disabled source UNLEASH check: {context}")
    res = bool(UNLEASH_CLIENT.is_enabled("cost-management.backend.disable-source", context))
    LOG.info(f"    Processing {'disabled' if res else 'enabled'} for source {source_uuid}")
    return res
