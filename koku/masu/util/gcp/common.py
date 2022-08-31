#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP utility functions and vars."""
import datetime
import json
import logging
import uuid
from json.decoder import JSONDecodeError

import ciso8601
import pandas as pd
from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from masu.util.ocp.common import match_openshift_labels

LOG = logging.getLogger(__name__)
pd.options.mode.chained_assignment = None


def get_bills_from_provider(provider_uuid, schema, start_date=None, end_date=None):
    """
    Return the GCP bill IDs given a provider UUID.

    Args:
        provider_uuid (str): Provider UUID.
        schema (str): Tenant schema
        start_date (datetime, str): Start date for bill IDs.
        end_date (datetime, str) End date for bill IDs.

    Returns:
        (list): GCP cost entry bill objects.

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

    if provider.type not in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
        err_msg = f"Provider UUID is not an GCP type.  It is {provider.type}"
        LOG.warning(err_msg)
        return []

    with GCPReportDBAccessor(schema) as report_accessor:
        with schema_context(schema):
            bills = report_accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            if start_date:
                bills = bills.filter(billing_period_start__gte=start_date)
            if end_date:
                bills = bills.filter(billing_period_start__lte=end_date)
            bills = bills.all()

    return bills


def process_gcp_labels(label_string):
    """Convert the report string to a JSON dictionary.

    Args:
        label_string (str): The raw report string of pod labels

    Returns:
        (dict): The JSON dictionary made from the label string

    """
    label_dict = {}
    try:
        if label_string:
            labels = json.loads(label_string)
            label_dict = {entry.get("key"): entry.get("value") for entry in labels}
    except JSONDecodeError:
        LOG.warning("Unable to process GCP labels.")

    return json.dumps(label_dict)


def process_gcp_credits(credit_string):
    """Process the credits column, which is non-standard JSON."""
    credit_dict = {}
    try:
        credits = json.loads(credit_string.replace("'", '"').replace("None", '"None"'))
        if credits:
            credit_dict = credits[0]
    except JSONDecodeError:
        LOG.warning("Unable to process GCP credits.")

    return json.dumps(credit_dict)


def gcp_post_processor(data_frame):
    """Guarantee column order for GCP parquet files"""
    columns = list(data_frame)
    column_name_map = {}
    for column in columns:
        new_col_name = strip_characters_from_column_name(column)
        column_name_map[column] = new_col_name
    data_frame = data_frame.rename(columns=column_name_map)

    label_set = set()
    unique_labels = data_frame.labels.unique()
    for label in unique_labels:
        label_set.update(json.loads(label).keys())

    return (data_frame, label_set)


def get_column_converters():
    """Return source specific parquet column converters."""
    return {
        "usage_start_time": ciso8601.parse_datetime,
        "usage_end_time": ciso8601.parse_datetime,
        "project.labels": process_gcp_labels,
        "labels": process_gcp_labels,
        "system_labels": process_gcp_labels,
        "export_time": ciso8601.parse_datetime,
        "cost": safe_float,
        "currency_conversion_rate": safe_float,
        "usage.amount": safe_float,
        "usage.amount_in_pricing_units": safe_float,
        "credits": process_gcp_credits,
    }


def gcp_generate_daily_data(data_frame):
    """Given a dataframe, return the data frame if its empty, group the data to create daily data."""
    if data_frame.empty:
        return data_frame

    # this parses the credits column into just the dollar amount so we can sum it up for daily rollups
    rollup_frame = data_frame.copy()
    rollup_frame["credits"] = rollup_frame["credits"].apply(json.loads)
    rollup_frame["daily_credits"] = 0.0
    for i, credit_dict in enumerate(rollup_frame["credits"]):
        rollup_frame["daily_credits"][i] = credit_dict.get("amount", 0.0)
    daily_data_frame = rollup_frame.groupby(
        [
            "invoice_month",
            "billing_account_id",
            "project_id",
            pd.Grouper(key="usage_start_time", freq="D"),
            "service_id",
            "sku_id",
            "system_labels",
            "labels",
            "cost_type",
            "location_region",
        ],
        dropna=False,
    ).agg(
        {
            "project_name": ["max"],
            "service_description": ["max"],
            "sku_description": ["max"],
            "usage_pricing_unit": ["max"],
            "usage_amount_in_pricing_units": ["sum"],
            "currency": ["max"],
            "cost": ["sum"],
            "daily_credits": ["sum"],
        }
    )
    columns = daily_data_frame.columns.droplevel(1)
    daily_data_frame.columns = columns
    daily_data_frame.reset_index(inplace=True)

    return daily_data_frame


def match_openshift_resources_and_labels(data_frame, cluster_topology, matched_tags):
    """Filter a dataframe to the subset that matches an OpenShift source."""
    tags = data_frame["labels"]
    tags = tags.str.lower()

    cluster_id = cluster_topology.get("cluster_id")
    cluster_alias = cluster_topology.get("cluster_alias")

    LOG.info("Matching OpenShift on GCP by labels.")
    ocp_matched = tags.str.contains(f"kubernetes-io-cluster-{cluster_id}|kubernetes-io-cluster-{cluster_alias}")

    data_frame["ocp_matched"] = ocp_matched
    data_frame["cluster_id"] = cluster_id

    special_case_tag_matched = tags.str.contains(
        "|".join(
            [
                f"openshift_cluster.*{cluster_id}",
                f"openshift_cluster.*{cluster_alias}",
                "openshift_project",
                "openshift_node",
            ]
        )
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

            LOG.info("Matching OpenShift on GCP tags.")

            matched_tag = tag_subset.apply(match_openshift_labels, args=(matched_tags,))
            data_frame["matched_tag"] = matched_tag
            data_frame["matched_tag"].fillna(value="", inplace=True)
        else:
            data_frame["matched_tag"] = ""
    else:
        data_frame["tag_matched"] = False
        data_frame["matched_tag"] = ""
    openshift_matched_data_frame = data_frame[
        (data_frame["ocp_matched"] == True)  # noqa: E712
        | (data_frame["special_case_tag_matched"] == True)  # noqa: E712
        | (data_frame["matched_tag"] != "")  # noqa: E712
    ]

    openshift_matched_data_frame["uuid"] = openshift_matched_data_frame.apply(lambda _: str(uuid.uuid4()), axis=1)
    openshift_matched_data_frame = openshift_matched_data_frame.drop(
        columns=["special_case_tag_matched", "tag_matched", "ocp_matched"]
    )

    return openshift_matched_data_frame


def deduplicate_reports_for_gcp(report_list):
    """Deduplicate the reports using the invoice."""
    invoice_dict = {}
    for report in report_list:
        invoice = report.get("invoice_month")
        start_key = invoice + "_start"
        end_key = invoice + "_end"
        if not invoice_dict.get(start_key) or not invoice_dict.get(end_key):
            invoice_dict[start_key] = [report.get("start")]
            invoice_dict[end_key] = [report.get("end")]
        else:
            invoice_dict[start_key].append(report.get("start"))
            invoice_dict[end_key].append(report.get("end"))

    restructure_dict = {}
    reports_deduplicated = []
    for invoice_key, date_list in invoice_dict.items():
        invoice_month, date_term = invoice_key.split("_")
        if date_term == "start":
            date_agg = min(date_list)
        else:
            date_agg = max(date_list)
        if restructure_dict.get(invoice_month):
            restructure_dict[invoice_month][date_term] = date_agg
        else:
            restructure_dict[invoice_month] = {date_term: date_agg}

    for invoice_month, date_dict in restructure_dict.items():
        reports_deduplicated.append(
            {
                "manifest_id": report.get("manifest_id"),
                "tracing_id": report.get("tracing_id"),
                "schema_name": report.get("schema_name"),
                "provider_type": report.get("provider_type"),
                "provider_uuid": report.get("provider_uuid"),
                "start": date_dict.get("start"),
                "end": date_dict.get("end"),
                "invoice_month": invoice_month,
            }
        )
    return reports_deduplicated
