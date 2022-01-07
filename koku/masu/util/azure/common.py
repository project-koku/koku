#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import datetime
import json
import logging
import re
import uuid

import ciso8601
import numpy as np
import pandas as pd
from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from masu.util.ocp.common import match_openshift_labels
from reporting.provider.azure.models import PRESTO_COLUMNS

LOG = logging.getLogger(__name__)


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

    with ProviderDBAccessor(provider_uuid) as provider_accessor:
        provider = provider_accessor.get_provider()

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
            bills = bills.all()

    return bills


def azure_date_converter(date):
    """Convert Azure date fields properly."""
    if date:
        try:
            new_date = ciso8601.parse_datetime(date)
        except ValueError:
            date_split = date.split("/")
            new_date_str = date_split[2] + date_split[0] + date_split[1]
            new_date = ciso8601.parse_datetime(new_date_str)
        return new_date
    else:
        return np.nan


def azure_json_converter(tag_str):
    """Convert either Azure JSON field format to proper JSON."""
    tag_dict = {}
    try:
        if "{" in tag_str:
            tag_dict = json.loads(tag_str)
        else:
            tags = tag_str.split('","')
            for tag in tags:
                key, value = tag.split(": ")
                tag_dict[key.strip('"')] = value.strip('"')
    except (ValueError, TypeError):
        pass

    return json.dumps(tag_dict)


def azure_post_processor(data_frame):
    """Guarantee column order for Azure parquet files"""
    columns = list(data_frame)
    column_name_map = {}

    for column in columns:
        new_col_name = strip_characters_from_column_name(column)
        column_name_map[column] = new_col_name

    data_frame = data_frame.rename(columns=column_name_map)

    columns = set(list(data_frame))
    columns = set(PRESTO_COLUMNS).union(columns)
    columns = sorted(columns)

    data_frame = data_frame.reindex(columns=columns)

    return data_frame


def get_column_converters():
    """Return source specific parquet column converters."""
    return {
        "usagedatetime": azure_date_converter,
        "date": azure_date_converter,
        "billingperiodstartdate": azure_date_converter,
        "billingperiodenddate": azure_date_converter,
        "usagequantity": safe_float,
        "quantity": safe_float,
        "resourcerate": safe_float,
        "pretaxcost": safe_float,
        "costinbillingcurrency": safe_float,
        "effectiveprice": safe_float,
        "unitprice": safe_float,
        "paygprice": safe_float,
        "tags": azure_json_converter,
        "additionalinfo": azure_json_converter,
    }


def azure_generate_daily_data(data_frame):
    """Return the Azure data frame, as it is already daily."""
    return data_frame


def match_openshift_resources_and_labels(data_frame, cluster_topology, matched_tags):
    """Filter a dataframe to the subset that matches an OpenShift source."""
    nodes = cluster_topology.get("nodes", [])
    volumes = cluster_topology.get("persistent_volumes", [])
    matchable_resources = nodes + volumes
    resource_id_df = data_frame["resourceid"]
    if resource_id_df.isna().values.all():
        resource_id_df = data_frame["instanceid"]

    LOG.info("Matching OpenShift on Azure by resource ID.")
    resource_id_matched = resource_id_df.str.contains("|".join(matchable_resources))
    data_frame["resource_id_matched"] = resource_id_matched

    tags = data_frame["tags"]
    tags = tags.str.lower()

    special_case_tag_matched = tags.str.contains(
        "|".join(["openshift_cluster", "openshift_project", "openshift_node"])
    )
    data_frame["special_case_tag_matched"] = special_case_tag_matched

    if matched_tags:
        tag_keys = []
        tag_values = []
        for tag in matched_tags:
            tag_keys.extend(list(tag.keys()))
            tag_values.extend(list(tag.values()))

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
            data_frame["matched_tag"].fillna(value="", inplace=True)
        else:
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
