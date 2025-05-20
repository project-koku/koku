#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for OCP Parquet files."""
import datetime
import logging

import ciso8601
from django.conf import settings
from django_tenants.utils import schema_context

from api.common import log_json
from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.util.common import month_date_range
from masu.util.ocp import common as utils
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import TRINO_LINE_ITEM_TABLE_DAILY_MAP
from reporting.provider.ocp.models import TRINO_LINE_ITEM_TABLE_MAP

LOG = logging.getLogger(__name__)


class OCPReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path, report_type):
        if "daily" in s3_path:
            ocp_table_name = TRINO_LINE_ITEM_TABLE_DAILY_MAP[report_type]
        else:
            ocp_table_name = TRINO_LINE_ITEM_TABLE_MAP[report_type]
        numeric_columns = [
            "pod_usage_cpu_core_seconds",
            "pod_request_cpu_core_seconds",
            "pod_effective_usage_cpu_core_seconds",
            "pod_limit_cpu_core_seconds",
            "pod_usage_memory_byte_seconds",
            "pod_request_memory_byte_seconds",
            "pod_effective_usage_memory_byte_seconds",
            "pod_limit_memory_byte_seconds",
            "node_capacity_cpu_cores",
            "node_capacity_cpu_core_seconds",
            "node_capacity_memory_bytes",
            "node_capacity_memory_byte_seconds",
            "persistentvolumeclaim_usage_byte_seconds",
            "volume_request_storage_byte_seconds",
            "persistentvolumeclaim_capacity_byte_seconds",
            "persistentvolumeclaim_capacity_bytes",
            "vm_uptime_total_seconds",
            "vm_cpu_limit_core_seconds",
            "vm_cpu_request_cores",
            "vm_cpu_request_core_seconds",
            "vm_cpu_request_sockets",
            "vm_cpu_request_socket_seconds",
            "vm_cpu_request_threads",
            "vm_cpu_request_thread_seconds",
            "vm_cpu_usage_total_seconds",
            "vm_memory_limit_bytes",
            "vm_memory_limit_byte_seconds",
            "vm_memory_request_bytes",
            "vm_memory_request_byte_seconds",
            "vm_memory_usage_byte_seconds",
            "vm_disk_allocated_size_byte_seconds",
        ]
        date_columns = ["report_period_start", "report_period_end", "interval_start", "interval_end"]
        column_types = {"numeric_columns": numeric_columns, "date_columns": date_columns, "boolean_columns": []}
        super().__init__(
            manifest_id=manifest_id,
            account=account,
            s3_path=s3_path,
            provider_uuid=provider_uuid,
            parquet_local_path=parquet_local_path,
            column_types=column_types,
            table_name=ocp_table_name,
        )

    @property
    def postgres_summary_table(self):
        """Return the mode for the source specific summary table."""
        return OCPUsageLineItemDailySummary

    def create_bill(self, bill_date):
        """Create bill postgres entry."""
        if isinstance(bill_date, str):
            bill_date = ciso8601.parse_datetime(bill_date)
        report_date_range = month_date_range(bill_date)
        start_date, end_date = report_date_range.split("-")

        report_period_start = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, tzinfo=settings.UTC)
        report_period_end = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, tzinfo=settings.UTC)
        # Make end date first of next month
        report_period_end = report_period_end + datetime.timedelta(days=1)

        provider = self._get_provider()

        cluster_id = utils.get_cluster_id_from_provider(provider.uuid)
        cluster_alias = utils.get_cluster_alias_from_cluster_id(cluster_id)

        LOG.info(
            log_json(
                msg="getting or creating bill",
                cluster_id=cluster_id,
                cluster_alias=cluster_alias,
                provider_uuid=provider.uuid,
                provider_name=provider.name,
                provider_type=provider.type,
                schema=self._schema_name,
            )
        )
        with schema_context(self._schema_name):
            bill, _ = OCPUsageReportPeriod.objects.get_or_create(
                cluster_id=cluster_id,
                report_period_start=report_period_start,
                report_period_end=report_period_end,
                provider_id=provider.uuid,
            )
            if bill.cluster_alias != cluster_alias:
                bill.cluster_alias = cluster_alias
                bill.save(update_fields=["cluster_alias"])
