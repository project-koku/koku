#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from api.query_filter import QueryFilterCollection
from masu.processor import GCP_UNATTRIBUTED_STORAGE_UNLEASH_FLAG
from masu.processor import is_feature_flag_enabled_by_account


def gcp_storage_conditional_filter_collection(schema_name):
    """Builds the GCP storage filters"""

    storage_services = QueryFilterCollection()
    storage_services.add(
        field="service_alias", operation="in", parameter=["Filestore", "Data Transfer", "Storage", "Cloud Storage"]
    )
    unattributed_stroage_enabled = is_feature_flag_enabled_by_account(
        schema_name, GCP_UNATTRIBUTED_STORAGE_UNLEASH_FLAG
    )
    if not unattributed_stroage_enabled:
        return storage_services.compose()

    compute_engine = QueryFilterCollection()
    compute_engine.add(field="service_alias", operation="exact", parameter="Compute Engine")

    sku_alias = QueryFilterCollection()
    sku_alias.add(field="sku_alias", operation="icontains", parameter=" pd ")
    sku_alias.add(field="sku_alias", operation="icontains", parameter=" snapshot ")
    persistent_disk_composed = compute_engine.compose() & sku_alias.compose(logical_operator="or")
    return storage_services.compose() | persistent_disk_composed
