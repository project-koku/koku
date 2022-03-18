#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import logging

import ciso8601

from masu.util.common import safe_float

LOG = logging.getLogger(__name__)

"""OCI utility functions and vars."""

# TODO NEeds updating to match OCI data types
OCI_SERVICE_LINE_ITEM_TYPE_MAP = {
    "Compute Engine": "usage",
    "Kubernetes Engine": "usage",
    "Cloud Functions": "usage",
    "Clould Run": "usage",
    "VMware Engine": "usage",
    "Filestore": "storage",
    "Storage": "storage",
    "Data Transfer": "storage",
    "VPC network": "network",
    "Network services": "network",
    "Hybrid Connectivity": "network",
    "Network Service Tiers": "network",
    "Network Security": "network",
    "Network Intelligence": "network",
    "Bigtable": "database",
    "Datastore": "database",
    "Database Migrations": "database",
    "Firestore": "database",
    "MemoryStore": "database",
    "Spanner": "database",
    "SQL": "database",
}


def get_column_converters():
    """Return source specific parquet column converters."""
    return {
        "bill/billingperiodstartdate": ciso8601.parse_datetime,
        "bill/billingperiodenddate": ciso8601.parse_datetime,
        "lineitem/usagestartdate": ciso8601.parse_datetime,
        "lineitem/usageenddate": ciso8601.parse_datetime,
        "lineitem/usageamount": safe_float,
        "lineitem/normalizationfactor": safe_float,
        "lineitem/normalizedusageamount": safe_float,
        "lineitem/unblendedrate": safe_float,
        "lineitem/unblendedcost": safe_float,
        "lineitem/blendedrate": safe_float,
        "lineitem/blendedcost": safe_float,
        "pricing/publicondemandcost": safe_float,
        "pricing/publicondemandrate": safe_float,
        "savingsplan/savingsplaneffectivecost": safe_float,
    }
