#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

from api.query_filter import QueryFilterCollection

LOG = logging.getLogger(__name__)


def gcp_storage_conditional_filter_collection():
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


def ocp_all_storage_filter_collection():
    """Builds the storage filters for all cloud providers."""
    service_filters = QueryFilterCollection()
    service_filters.add(field="product_code", operation="icontains", parameter="Storage")  # Azure & GCP
    service_filters.add(field="product_family", operation="icontains", parameter="Storage")  # AWS
    service_filters.add(
        field="product_code", operation="in", parameter=["Filestore", "Data Transfer", "Compute Engine"]
    )  # GCP
    unit_filters = QueryFilterCollection()
    unit_filters.add(field="unit", operation="in", parameter=["GB-Mo", "gibibyte month"])
    return unit_filters.compose() & service_filters.compose(logical_operator="or")
