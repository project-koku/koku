#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import datetime
import json
import logging

import ciso8601
import pandas as pd
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from masu.database.oci_report_db_accessor import OCIReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name
from reporting.provider.oci.models import PRESTO_REQUIRED_COLUMNS


LOG = logging.getLogger(__name__)


def get_column_converters():
    """Return source specific parquet column converters."""
    return {
        "bill/billingperiodstartdate": ciso8601.parse_datetime,
        "bill/billingperiodenddate": ciso8601.parse_datetime,
        "lineitem/intervalusagestart": ciso8601.parse_datetime,
        "lineitem/intervalusageend": ciso8601.parse_datetime,
        "usage/consumedquantity": safe_float,
        "cost/mycost": safe_float,
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


def oci_post_processor(data_frame):
    """
    Consume the OCI data and add a column creating a dictionary for the oci tags
    """

    def scrub_resource_col_name(res_col_name):
        return res_col_name.split(".")[-1]

    columns = set(list(data_frame))
    columns = set(PRESTO_REQUIRED_COLUMNS).union(columns)
    columns = sorted(list(columns))

    resource_tag_columns = [column for column in columns if "tags/" in column]
    unique_keys = {scrub_resource_col_name(column) for column in resource_tag_columns}
    tag_df = data_frame[resource_tag_columns]
    resource_tags_dict = tag_df.apply(
        lambda row: {scrub_resource_col_name(column): value for column, value in row.items() if value}, axis=1
    )
    resource_tags_dict.where(resource_tags_dict.notna(), lambda _: [{}], inplace=True)

    data_frame["tags"] = resource_tags_dict.apply(json.dumps)
    # Make sure we have entries for our required columns
    data_frame = data_frame.reindex(columns=columns)

    columns = list(data_frame)
    column_name_map = {}
    drop_columns = []
    for column in columns:
        new_col_name = strip_characters_from_column_name(column)
        column_name_map[column] = new_col_name
        if "tags/" in column:
            drop_columns.append(column)
    data_frame = data_frame.drop(columns=drop_columns)
    data_frame = data_frame.rename(columns=column_name_map)
    return (data_frame, unique_keys)


def oci_generate_daily_data(data_frame):
    """Given a dataframe, group the data to create daily data."""

    if "cost_mycost" in data_frame:
        daily_data_frame = data_frame.groupby(
            [
                "product_resourceid",
                pd.Grouper(key="lineitem_intervalusagestart", freq="D"),
                "lineitem_tenantid",
                "product_service",
                "product_region",
                "tags",
            ],
            dropna=False,
        ).agg({"cost_currencycode": ["max"], "cost_mycost": ["sum"]})
    else:
        daily_data_frame = data_frame.groupby(
            [
                "product_resourceid",
                pd.Grouper(key="lineitem_intervalusagestart", freq="D"),
                "lineitem_tenantid",
                "product_service",
                "product_region",
                "tags",
            ],
            dropna=False,
        ).agg({"usage_consumedquantity": ["sum"]})
    columns = daily_data_frame.columns.droplevel(1)
    daily_data_frame.columns = columns
    daily_data_frame.reset_index(inplace=True)

    return daily_data_frame


def detect_type(report_path):
    """
    Detects the OCI report type.
    """
    sorted_columns = sorted(pd.read_csv(report_path, nrows=0).columns)
    if "cost/myCost" in sorted_columns:
        report_type = "cost"
    else:
        report_type = "usage"
    return report_type


def deduplicate_reports_for_oci(report_list):
    """Remove deduplicate oci manifests"""
    manifest_id_set = set()
    reports_deduplicated = []
    for report in report_list:
        _manifest_id = report.get("manifest_id")
        if _manifest_id and _manifest_id not in manifest_id_set:
            reports_deduplicated.append(
                {
                    "manifest_id": _manifest_id,
                    "tracing_id": report.get("tracing_id"),
                    "schema_name": report.get("schema_name"),
                    "provider_type": report.get("provider_type"),
                    "provider_uuid": report.get("provider_uuid"),
                    "start": report.get("start"),
                    "end": report.get("end"),
                    "invoice_month": None,
                }
            )
            manifest_id_set.add(_manifest_id)
    return reports_deduplicated
