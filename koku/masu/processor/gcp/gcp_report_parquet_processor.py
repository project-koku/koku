#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for GCP Parquet files."""
import ciso8601
from django.conf import settings
from django_tenants.utils import schema_context

from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.util import common as utils
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.gcp.models import TRINO_LINE_ITEM_TABLE
from reporting.provider.gcp.models import TRINO_OCP_ON_GCP_DAILY_TABLE


class GCPReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, start_date):
        numeric_columns = [
            "cost",
            "currency_conversion_rate",
            "usage_amount",
            "usage_amount_in_pricing_units",
            "credit_amount",
            "daily_credits",
        ]
        date_columns = ["usage_start_time", "usage_end_time", "export_time", "partition_time"]
        boolean_columns = ["ocp_matched"]
        if "openshift" in s3_path:
            table_name = TRINO_OCP_ON_GCP_DAILY_TABLE
        elif "daily" in s3_path:
            table_name = TRINO_LINE_ITEM_DAILY_TABLE
        else:
            table_name = TRINO_LINE_ITEM_TABLE
        column_types = {
            "numeric_columns": numeric_columns,
            "date_columns": date_columns,
            "boolean_columns": boolean_columns,
        }
        super().__init__(
            manifest_id=manifest_id,
            account=account,
            s3_path=s3_path,
            provider_uuid=provider_uuid,
            column_types=column_types,
            table_name=table_name,
            start_date=start_date,
        )

    @property
    def postgres_summary_table(self):
        """Return the mode for the source specific summary table."""
        return GCPCostEntryLineItemDailySummary

    def create_bill(self, bill_date):
        """Create bill postgres entry."""
        if isinstance(bill_date, str):
            bill_date = ciso8601.parse_datetime(bill_date)
        report_date_range = utils.month_date_range(bill_date)
        start_date, end_date = report_date_range.split("-")

        start_date_utc = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, tzinfo=settings.UTC)
        end_date_utc = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, tzinfo=settings.UTC)

        provider = self._get_provider()

        with schema_context(self._schema_name):
            GCPCostEntryBill.objects.get_or_create(
                billing_period_start=start_date_utc,
                billing_period_end=end_date_utc,
                provider_id=provider.uuid,
            )

    def _generate_create_table_sql(self, column_names):
        column_names.append("manifestid")
        return super()._generate_create_table_sql(column_names)
