#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Apply tag mappings to already-summarized rows and refresh tag-derived tables.

Summary updaters insert unmapped labels, then call ``apply_tag_mappings``.
A tag-mapping edit calls the same function without rebuilding from parquet/Trino.

Accessors here are instantiated without ``with``. ``ReportDBAccessorBase.__exit__``
always ``set_schema_to_public()``, which would undo a caller already on the
tenant schema (OCP/cloud parquet summary then ``bill.save()`` / ``report_period.save()``).
"""
import logging

from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from api.utils import to_date
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor import is_feature_cost_4403_ec2_compute_cost_enabled
from masu.util.common import SummaryRangeConfig
from reporting.provider.ocp.models import VM_UI_SUMMARY_TABLE

LOG = logging.getLogger(__name__)

ROW_SCOPE_USAGE = "usage"
ROW_SCOPE_INFRA = "infra"
ROW_SCOPE_ALL = "all"

_OCP_TYPES = (Provider.PROVIDER_OCP,)
_AWS_TYPES = (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL)
_AZURE_TYPES = (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL)
_GCP_TYPES = (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL)


def apply_tag_mappings(
    schema,
    provider,
    start_date,
    end_date,
    *,
    row_scope=ROW_SCOPE_ALL,
    include_linked_ocp_on_cloud=False,
):
    """Map child tag keys to parents on summarized rows, then rebuild tag-derived tables.

    Args:
        schema (str): Customer schema name.
        provider (Provider): Source whose summarized rows should be mapped.
        start_date, end_date: Inclusive range (date, datetime, or parseable string).
        row_scope (str): For OCP daily summary, which rows to map
            (``usage``, ``infra``, or ``all``). Ignored for cloud providers.
        include_linked_ocp_on_cloud (bool): Also map OCP-on-cloud project tables
            for this OCP cluster or for clusters on this cloud account.
    """
    start_date = to_date(start_date)
    end_date = to_date(end_date)
    context = {
        "schema": schema,
        "provider_uuid": str(provider.uuid),
        "provider_type": provider.type,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "row_scope": row_scope,
        "include_linked_ocp_on_cloud": include_linked_ocp_on_cloud,
    }
    LOG.info(log_json(msg="applying tag mappings", context=context))

    if provider.type in _OCP_TYPES:
        _apply_ocp_tag_mappings(schema, provider, start_date, end_date, row_scope)
        if include_linked_ocp_on_cloud:
            _apply_ocp_on_cloud_tag_mappings_for_ocp(schema, provider, start_date, end_date)
        return

    if provider.type in _AWS_TYPES:
        _apply_aws_tag_mappings(schema, provider, start_date, end_date)
    elif provider.type in _AZURE_TYPES:
        _apply_azure_tag_mappings(schema, provider, start_date, end_date)
    elif provider.type in _GCP_TYPES:
        _apply_gcp_tag_mappings(schema, provider, start_date, end_date)
    else:
        LOG.info(log_json(msg="skipping tag mappings; unsupported provider type", context=context))
        return

    if include_linked_ocp_on_cloud:
        _apply_ocp_on_cloud_tag_mappings_for_cloud(schema, provider, start_date, end_date)


def _apply_ocp_tag_mappings(schema, provider, start_date, end_date, row_scope):
    """Map OCP daily-summary rows and rebuild label summaries plus VM UI."""
    with schema_context(schema):
        accessor = OCPReportDBAccessor(schema)
        report_period = accessor.report_periods_for_provider_uuid(provider.uuid, start_date)
        if not report_period:
            LOG.info(
                log_json(
                    msg="no OCP report period; skipping tag mappings",
                    context={
                        "schema": schema,
                        "provider_uuid": str(provider.uuid),
                        "start_date": str(start_date),
                    },
                )
            )
            return
        report_period_ids = [report_period.id]
        if row_scope in (ROW_SCOPE_USAGE, ROW_SCOPE_ALL):
            accessor.update_line_item_daily_summary_with_tag_mapping(
                start_date, end_date, report_period_ids, infrastructure_only=False
            )
        if row_scope in (ROW_SCOPE_INFRA, ROW_SCOPE_ALL):
            accessor.update_line_item_daily_summary_with_tag_mapping(
                start_date, end_date, report_period_ids, infrastructure_only=True
            )
        if row_scope in (ROW_SCOPE_USAGE, ROW_SCOPE_ALL):
            accessor.populate_pod_label_summary_table(report_period_ids, start_date, end_date)
            accessor.populate_volume_label_summary_table(report_period_ids, start_date, end_date)
            accessor.populate_ui_summary_tables(
                SummaryRangeConfig(start_date=start_date, end_date=end_date),
                provider.uuid,
                tables=(VM_UI_SUMMARY_TABLE,),
            )


def _apply_aws_tag_mappings(schema, provider, start_date, end_date):
    """Map AWS daily summary (and EC2 compute summary) then rebuild tags summary."""
    with schema_context(schema):
        accessor = AWSReportDBAccessor(schema)
        bill_ids = _bill_ids(accessor, provider.uuid, start_date)
        accessor.update_line_item_daily_summary_with_tag_mapping(start_date, end_date, bill_ids)
        if is_feature_cost_4403_ec2_compute_cost_enabled(schema):
            month_start = start_date.replace(day=1) if hasattr(start_date, "replace") else start_date
            accessor.update_line_item_daily_summary_with_tag_mapping(
                month_start,
                end_date,
                bill_ids,
                table_name=AWS_CUR_TABLE_MAP["ec2_compute_summary"],
            )
        accessor.populate_tags_summary_table(bill_ids, start_date, end_date)


def _apply_azure_tag_mappings(schema, provider, start_date, end_date):
    """Map Azure daily summary then rebuild tags summary."""
    with schema_context(schema):
        accessor = AzureReportDBAccessor(schema)
        bill_ids = _bill_ids(accessor, provider.uuid, start_date)
        accessor.update_line_item_daily_summary_with_tag_mapping(start_date, end_date, bill_ids)
        accessor.populate_tags_summary_table(bill_ids, start_date, end_date)


def _apply_gcp_tag_mappings(schema, provider, start_date, end_date):
    """Map GCP daily summary then rebuild tags summary."""
    with schema_context(schema):
        accessor = GCPReportDBAccessor(schema)
        bill_ids = _bill_ids(accessor, provider.uuid, start_date)
        accessor.update_line_item_daily_summary_with_tag_mapping(start_date, end_date, bill_ids)
        accessor.populate_tags_summary_table(bill_ids, start_date, end_date)


def _apply_ocp_on_cloud_tag_mappings_for_ocp(schema, provider, start_date, end_date):
    """Map OCP-on-cloud project tables for a single OpenShift cluster."""
    infra = provider.infrastructure
    if not infra:
        return
    _apply_ocp_on_cloud_tag_mappings(
        schema,
        provider,
        infra.infrastructure_provider_id,
        infra.infrastructure_type,
        start_date,
        end_date,
    )


def _apply_ocp_on_cloud_tag_mappings_for_cloud(schema, cloud_provider, start_date, end_date):
    """Map OCP-on-cloud project tables for every cluster on this cloud account."""
    ocp_providers = Provider.objects.filter(infrastructure__infrastructure_provider_id=cloud_provider.uuid)
    for ocp_provider in ocp_providers:
        _apply_ocp_on_cloud_tag_mappings(
            schema,
            ocp_provider,
            cloud_provider.uuid,
            cloud_provider.type,
            start_date,
            end_date,
        )


def _apply_ocp_on_cloud_tag_mappings(schema, ocp_provider, infra_uuid, infra_type, start_date, end_date):
    """Map one cluster's OCP-on-cloud project daily summary and rebuild its tags summary."""
    with schema_context(schema):
        report_period = OCPReportDBAccessor(schema).report_periods_for_provider_uuid(ocp_provider.uuid, start_date)
        if not report_period:
            return

        if infra_type in _AWS_TYPES:
            accessor = AWSReportDBAccessor(schema)
            bill_ids = _bill_ids(accessor, infra_uuid, start_date)
            if not bill_ids:
                return
            accessor.populate_ocp_on_aws_tag_information(bill_ids, start_date, end_date, report_period.id)
        elif infra_type in _AZURE_TYPES:
            accessor = AzureReportDBAccessor(schema)
            bill_ids = _bill_ids(accessor, infra_uuid, start_date)
            if not bill_ids:
                return
            accessor.populate_ocp_on_azure_tag_information(bill_ids, start_date, end_date, report_period.id)
        elif infra_type in _GCP_TYPES:
            accessor = GCPReportDBAccessor(schema)
            bill_ids = _bill_ids(accessor, infra_uuid, start_date)
            if not bill_ids:
                return
            accessor.populate_ocp_on_gcp_tag_information(bill_ids, start_date, end_date, report_period.id)


def _bill_ids(accessor, provider_uuid, start_date):
    """Return bill ids for provider and month, or None if the accessor has none."""
    with schema_context(accessor.schema):
        bills = accessor.bills_for_provider_uuid(provider_uuid, start_date)
        return [str(bill.id) for bill in bills]
