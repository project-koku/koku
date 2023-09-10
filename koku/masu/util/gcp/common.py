#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP utility functions and vars."""
import datetime
import logging
import uuid

import pandas as pd
from django_tenants.utils import schema_context

from api.models import Provider
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.processor import is_gcp_resource_matching_disabled
from masu.util.ocp.common import match_openshift_labels
from reporting.provider.gcp.models import GCPCostEntryBill

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

    with schema_context(schema):
        bills = GCPCostEntryBill.objects.filter(provider_id=provider.uuid)
        if start_date:
            bills = bills.filter(billing_period_start__gte=start_date)
        if end_date:
            bills = bills.filter(billing_period_start__lte=end_date)

        bills = list(bills.all())

    return bills


def match_openshift_resources_and_labels(data_frame, cluster_topologies, matched_tags):
    """Filter a dataframe to the subset that matches an OpenShift source."""
    tags = data_frame["labels"]
    tags = tags.str.lower()
    resource_id_df = data_frame.get("resource_name")
    match_columns = []

    for i, cluster_topology in enumerate(cluster_topologies):
        match_col_name = f"ocp_matched_{i}"
        cluster_id = cluster_topology.get("cluster_id", "")
        cluster_alias = cluster_topology.get("cluster_alias", "")
        nodes = list(filter(None, cluster_topology.get("nodes", [])))
        volumes = list(filter(None, cluster_topology.get("persistent_volumes", [])))
        matchable_resources = nodes + volumes

        if resource_id_df.any():
            LOG.info("Matching OpenShift on GCP by resource ID.")
            matching_check = "|".join(matchable_resources)
            if not matching_check:
                continue
            ocp_matched = resource_id_df.str.contains(matching_check)
        else:
            LOG.info("Matching OpenShift on GCP by labels.")
            cluster_strings = [
                f"kubernetes-io-cluster-{cluster_identifier}" for cluster_identifier in (cluster_id, cluster_alias)
            ]
            ocp_matched = tags.str.contains("|".join(cluster_strings))

        # Add in OCP Cluster these resources matched to
        data_frame[match_col_name] = ocp_matched
        data_frame.loc[data_frame[match_col_name] == True, "ocp_source_uuid"] = cluster_topology.get(  # noqa: E712
            "provider_uuid"
        )
        match_columns.append(match_col_name)

    # Consildate the columns per cluster into a single column
    data_frame.loc[data_frame["ocp_source_uuid"].notnull(), "ocp_matched"] = True
    data_frame = data_frame.drop(columns=match_columns)
    data_frame["ocp_source_uuid"].fillna(value="", inplace=True)

    special_case_tag_matched = tags.str.contains(
        "|".join(
            [
                "openshift_cluster",
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
        columns=["special_case_tag_matched", "tag_matched"]
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


def check_resource_level(gcp_provider_uuid):
    LOG.info("Fetching account for checking unleash resource level")
    try:
        account = AccountsAccessor().get_account_from_uuid(gcp_provider_uuid)
    except AccountsAccessorError:
        LOG.info("Account not returned, source likely has processing suspended.")
        return False

    if is_gcp_resource_matching_disabled(account.get("schema_name")):
        LOG.info(f"GCP resource matching disabled for {account.get('schema_name')}")
        return False
    if source := account.get("data_source"):
        if source.get("storage_only"):
            LOG.info("Storage only source defaults to resource level only")
            return True
        if "resource" in source.get("table_id"):
            LOG.info("OCP GCP matching set to resource level")
            return True

    LOG.info("Defaulting to GCP tag matching")
    return False


def add_label_columns(data_frame):
    label_data = False
    system_label_data = False
    columns = list(data_frame)
    for column in columns:
        if "labels" == column:
            label_data = True
        if "system_labels" == column:
            system_label_data = True
    if not label_data:
        data_frame["labels"] = ""
    if not system_label_data:
        data_frame["system_labels"] = ""
    return data_frame
