#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

from api.query_filter import QueryFilterCollection

LOG = logging.getLogger(__name__)


def gcp_storage_conditional_filter_collection(schema_name):
    """Builds the GCP storage filters"""

    storage_services = QueryFilterCollection()
    storage_services.add(
        field="service_alias", operation="in", parameter=["Filestore", "Data Transfer", "Storage", "Cloud Storage"]
    )
    compute_engine = QueryFilterCollection()
    compute_engine.add(field="service_alias", operation="exact", parameter="Compute Engine")

    sku_alias = QueryFilterCollection()
    sku_alias.add(field="sku_alias", operation="icontains", parameter=" pd ")
    sku_alias.add(field="sku_alias", operation="icontains", parameter=" snapshot ")
    persistent_disk_composed = compute_engine.compose() & sku_alias.compose(logical_operator="or")
    return storage_services.compose() | persistent_disk_composed
