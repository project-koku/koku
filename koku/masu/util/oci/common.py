#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import datetime
import logging

import ciso8601
import pandas as pd
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from masu.database.oci_report_db_accessor import OCIReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.util.common import safe_float
from masu.util.common import strip_characters_from_column_name


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
    """Guarantee column order for OCI parquet files"""
    # TODO This needs figuring out for tags
    columns = list(data_frame)
    column_name_map = {}
    drop_columns = []
    for column in columns:
        new_col_name = strip_characters_from_column_name(column)
        column_name_map[column] = new_col_name
        if "resourceTags/" in column:
            drop_columns.append(column)
    data_frame = data_frame.drop(columns=drop_columns)
    data_frame = data_frame.rename(columns=column_name_map)
    return data_frame


def oci_generate_daily_data(data_frame):
    """Given a dataframe, group the data to create daily data."""
    # usage_start = data_frame["lineitem_usagestartdate"]
    # usage_start_dates = usage_start.apply(lambda row: row.date())
    # data_frame["usage_start"] = usage_start_dates
    if "cost_mycost" in data_frame:
        daily_data_frame = data_frame.groupby(
            [
                "product_resourceid",
                pd.Grouper(key="lineitem_intervalusagestart", freq="D"),
                "lineitem_tenantid",
                "product_service",
                "product_region",
                "tags_oracle_tags_createdby",
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
                "tags_oracle_tags_createdby",
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
