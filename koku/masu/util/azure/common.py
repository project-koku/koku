#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import datetime
import logging
import re
from enum import Enum

from django_tenants.utils import schema_context

from api.models import Provider
from masu.database.azure_report_db_accessor import AzureReportDBAccessor

LOG = logging.getLogger(__name__)

INGRESS_REQUIRED_COLUMNS = {
    "additionalinfo",
    "billingaccountid",
    "billingaccountname",
    "billingperiodenddate",
    "billingperiodstartdate",
    "consumedservice",
    "costinbillingcurrency",
    "date",
    "effectiveprice",
    "metercategory",
    "meterid",
    "metername",
    "meterregion",
    "metersubcategory",
    "offerid",
    "productname",
    "publishername",
    "publishertype",
    "quantity",
    "reservationid",
    "reservationname",
    "resourceid",
    "resourcelocation",
    "resourcename",
    "servicefamily",
    "serviceinfo1",
    "serviceinfo2",
    "subscriptionid",
    "tags",
    "unitofmeasure",
    "unitprice",
}

INGRESS_REQUIRED_ALT_COLUMNS = [["billingcurrencycode", "billingcurrency"], ["resourcegroup", "resourcegroupname"]]

SUPPORTED_REPORT_TYPES = ["ActualCost", "AmortizedCost"]


class AzureBlobExtension(Enum):
    manifest = "_manifest.json"
    csv = ".csv"
    json = ".json"
    gzip = ".csv.gz"


def extract_uuids_from_string(source_string):
    """
    Extract uuids out of a given source string.

    Args:
        source_string (Source): string to locate UUIDs.

    Returns:
        ([]) List of UUIDs found in the source string

    """
    uuid_regex = "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    found_uuid = re.findall(uuid_regex, source_string, re.IGNORECASE)
    return found_uuid


def get_local_file_name(cur_key):
    """
    Return the local file name for a given cost usage report key.

    If an assemblyID is present in the key, it will prepend it to the filename.

    Args:
        cur_key (String): reportKey value from manifest file.
        example:
        With AssemblyID: /koku/20180701-20180801/882083b7-ea62-4aab-aa6a-f0d08d65ee2b/koku-1.csv.gz
        Without AssemblyID: /koku/20180701-20180801/koku-Manifest.json

    Returns:
        (String): file name for the local file,
                example:
                With AssemblyID: "882083b7-ea62-4aab-aa6a-f0d08d65ee2b-koku-1.csv.gz"
                Without AssemblyID: "koku-Manifest.json"

    """
    local_file_name = cur_key.split("/")[-1]

    return local_file_name


def get_bills_from_provider(provider_uuid, schema, start_date=None, end_date=None):
    """
    Return the Azure bill IDs given a provider UUID.

    Args:
        provider_uuid (str): Provider UUID.
        schema (str): Tenant schema
        start_date (datetime): Start date for bill IDs.
        end_date (datetime) End date for bill IDs.

    Returns:
        (list): Azure cost entry bill objects.

    """
    if isinstance(start_date, (datetime.datetime, datetime.date)):
        start_date = start_date.replace(day=1)
        start_date = start_date.strftime("%Y-%m-%d")

    if isinstance(end_date, (datetime.datetime, datetime.date)):
        end_date = end_date.strftime("%Y-%m-%d")

    provider = Provider.objects.filter(uuid=provider_uuid).first()
    if not provider:
        err_msg = "Provider UUID is not associated with a given provider."
        LOG.warning(err_msg)
        return []

    if provider.type not in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
        err_msg = f"Provider UUID is not an Azure type.  It is {provider.type}"
        LOG.warning(err_msg)
        return []

    with AzureReportDBAccessor(schema) as report_accessor:
        with schema_context(schema):
            bills = report_accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            if start_date:
                bills = bills.filter(billing_period_start__gte=start_date)
            if end_date:
                bills = bills.filter(billing_period_start__lte=end_date)
            # postgres doesn't always return this query in the same order, ordering by ID (PK) will
            # ensure that any list iteration or indexing is always done in the same order
            bills = list(bills.order_by("id").all())

    return bills
