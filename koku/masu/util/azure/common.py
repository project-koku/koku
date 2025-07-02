#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import datetime
import logging
import re
import uuid
from enum import Enum
from itertools import chain

import pandas as pd
from django_tenants.utils import schema_context

from api.models import Provider
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.util.ocp.common import match_openshift_labels

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


def match_openshift_resources_and_labels(data_frame, cluster_topologies, matched_tags):
    """Filter a dataframe to the subset that matches an OpenShift source."""
    nodes = chain.from_iterable(cluster_topology.get("nodes", []) for cluster_topology in cluster_topologies)
    volumes = chain.from_iterable(
        cluster_topology.get("persistent_volumes", []) for cluster_topology in cluster_topologies
    )
    csi_volume_handles = chain.from_iterable(
        cluster_topology.get("csi_volume_handle", []) for cluster_topology in cluster_topologies
    )
    matchable_resources = [*nodes, *volumes, *csi_volume_handles]
    matchable_resources = [x for x in matchable_resources if x is not None and x != ""]
    data_frame["resource_id_matched"] = False
    resource_id_df = data_frame["resourceid"]

    if not resource_id_df.eq("").all():
        LOG.info("Matching OpenShift on Azure by resource ID.")
        resource_id_matched = resource_id_df.str.contains("|".join(matchable_resources))
        data_frame["resource_id_matched"] = resource_id_matched

    data_frame["special_case_tag_matched"] = False
    tags = data_frame["tags"]
    if not tags.eq("").all():
        tags_lower = tags.str.lower()
        LOG.info("Matching OpenShift on Azure by tags.")
        special_case_tag_matched = tags_lower.str.contains(
            "|".join(["openshift_cluster", "openshift_project", "openshift_node"])
        )
        data_frame["special_case_tag_matched"] = special_case_tag_matched

    if matched_tags:
        tag_keys = []
        tag_values = []
        for tag in matched_tags:
            tag_keys.extend(list(tag.keys()))
            tag_values.extend(list(tag.values()))

        any_tag_matched = None
        if not tags.eq("").all():
            tag_matched = tags.str.contains("|".join(tag_keys)) & tags.str.contains("|".join(tag_values))
            data_frame["tag_matched"] = tag_matched
            any_tag_matched = tag_matched.any()

        if any_tag_matched:
            tag_df = pd.concat([tags, tag_matched], axis=1)
            tag_df.columns = ("tags", "tag_matched")
            tag_subset = tag_df[tag_df.tag_matched == True].tags  # noqa: E712

            LOG.info("Matching OpenShift on Azure tags.")

            matched_tag = tag_subset.apply(match_openshift_labels, args=(matched_tags,))
            data_frame["matched_tag"] = matched_tag
            data_frame["matched_tag"] = data_frame["matched_tag"].fillna(value="")
        else:
            data_frame["tag_matched"] = False
            data_frame["matched_tag"] = ""
    else:
        data_frame["tag_matched"] = False
        data_frame["matched_tag"] = ""

    openshift_matched_data_frame = data_frame[
        (data_frame["resource_id_matched"] == True)  # noqa: E712
        | (data_frame["special_case_tag_matched"] == True)  # noqa: E712
        | (data_frame["matched_tag"] != "")  # noqa: E712
    ]

    openshift_matched_data_frame["uuid"] = openshift_matched_data_frame.apply(lambda _: str(uuid.uuid4()), axis=1)
    openshift_matched_data_frame = openshift_matched_data_frame.drop(
        columns=["special_case_tag_matched", "tag_matched"]
    )

    return openshift_matched_data_frame
