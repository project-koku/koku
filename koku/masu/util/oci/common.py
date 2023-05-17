#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Common util functions."""
import datetime
import logging

import pandas as pd
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from masu.database.oci_report_db_accessor import OCIReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor


LOG = logging.getLogger(__name__)

OCI_REPORT_TYPES = {"cost", "usage"}


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
    """Remove duplicate oci manifests"""
    reports_deduplicated = []
    date_set = set()
    date_filtered_list = []
    for report in report_list:
        if report["start"] not in date_set:
            date_filtered_list.append(report)
            date_set.add(report["start"])

    manifest_id_list = [report["manifest_id"] for report in date_filtered_list]
    is_same_manifest_id = all(id == manifest_id_list[0] for id in manifest_id_list)

    if is_same_manifest_id:
        starts = []
        ends = []
        for report in date_filtered_list:
            if report.get("start") and report.get("end"):
                starts.append(report.get("start"))
                ends.append(report.get("end"))
        start_date = min(starts) if starts != [] else None
        end_date = max(ends) if ends != [] else None
        report = date_filtered_list[0]
        reports_deduplicated.append(
            {
                "manifest_id": report.get("manifest_id"),
                "tracing_id": report.get("tracing_id"),
                "schema_name": report.get("schema_name"),
                "provider_type": report.get("provider_type"),
                "provider_uuid": report.get("provider_uuid"),
                "start": start_date,
                "end": end_date,
            }
        )
    else:
        reports_deduplicated.extend(date_filtered_list)
    return reports_deduplicated
