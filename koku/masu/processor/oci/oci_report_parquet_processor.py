#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for OCI Parquet files."""
from zoneinfo import ZoneInfo

import ciso8601
from django_tenants.utils import schema_context

from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.util import common as utils
from reporting.provider.oci.models import OCICostEntryBill
from reporting.provider.oci.models import OCICostEntryLineItemDailySummary
from reporting.provider.oci.models import TRINO_LINE_ITEM_DAILY_TABLE_MAP
from reporting.provider.oci.models import TRINO_LINE_ITEM_TABLE_MAP


class OCIReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path, report_type):
        numeric_columns = ["usage_consumedquantity", "cost_mycost"]
        date_columns = [
            "lineitem_intervalusagestart",
            "lineitem_intervalusageend",
            "bill_billingperiodstartdate",
            "bill_billingperiodenddate",
        ]
        boolean_columns = ["resource_id_matched"]

        column_types = {
            "numeric_columns": numeric_columns,
            "date_columns": date_columns,
            "boolean_columns": boolean_columns,
        }
        if "daily" in s3_path:
            table_name = TRINO_LINE_ITEM_DAILY_TABLE_MAP[report_type]
        else:
            table_name = TRINO_LINE_ITEM_TABLE_MAP[report_type]
        super().__init__(
            manifest_id=manifest_id,
            account=account,
            s3_path=s3_path,
            provider_uuid=provider_uuid,
            parquet_local_path=parquet_local_path,
            column_types=column_types,
            table_name=table_name,
        )

    @property
    def postgres_summary_table(self):
        """Return the mode for the source specific summary table."""
        return OCICostEntryLineItemDailySummary

    def create_bill(self, bill_date):
        """Create bill postgres entry."""
        if isinstance(bill_date, str):
            bill_date = ciso8601.parse_datetime(bill_date)
        report_date_range = utils.month_date_range(bill_date)
        start_date, end_date = report_date_range.split("-")

        start_date_utc = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, tzinfo=ZoneInfo("UTC"))
        end_date_utc = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, tzinfo=ZoneInfo("UTC"))

        sql = f"""
            SELECT DISTINCT lineitem_tenantid
            FROM {self._table_name}
            WHERE source = '{self._provider_uuid}'
                AND year = '{bill_date.strftime("%Y")}'
                AND month = '{bill_date.strftime("%m")}'
        """
        rows = self._execute_sql(sql, self._schema_name)
        payer_tenant_id = None
        if rows:
            payer_tenant_id = rows[0][0]
        provider = self._get_provider()
        with schema_context(self._schema_name):
            OCICostEntryBill.objects.get_or_create(
                billing_period_start=start_date_utc,
                billing_period_end=end_date_utc,
                payer_tenant_id=payer_tenant_id,
                provider=provider,
            )
