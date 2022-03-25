#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import datetime
import logging

import ciso8601
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from masu.database.oci_report_db_accessor import OCIReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
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


def get_bills_from_provider(provider_uuid, schema, start_date=None, end_date=None):
    """
    Return the OCI bill IDs given a provider UUID.

    Args:
        provider_uuid (str): Provider UUID.
        schema (str): Tenant schema
        start_date (datetime, str): Start date for bill IDs.
        end_date (datetime, str) End date for bill IDs.

    Returns:
        (list): OCI cost entry bill objects.

    """
    if isinstance(start_date, (datetime.datetime, datetime.date)):
        start_date = start_date.replace(day=1)
        start_date = start_date.strftime("%Y-%m-%d")

    if isinstance(end_date, (datetime.datetime, datetime.date)):
        end_date = end_date.strftime("%Y-%m-%d")

    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        provider = provider_accessor.get_provider()

    if not provider:
        err_msg = "Provider UUID is not associated with a given provider."
        LOG.warning(err_msg)
        return []

    if provider.type not in (Provider.PROVIDER_OCI, Provider.PROVIDER_OCI_LOCAL):
        err_msg = f"Provider UUID is not an OCI type.  It is {provider.type}"
        LOG.warning(err_msg)
        return []

    with OCIReportDBAccessor(schema) as report_accessor:
        with schema_context(schema):
            bills = report_accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            if start_date:
                bills = bills.filter(billing_period_start__gte=start_date)
            if end_date:
                bills = bills.filter(billing_period_start__lte=end_date)
            bills = bills.all()

    return bills
