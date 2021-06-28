#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for Azure Parquet files."""
import logging

import ciso8601
import pytz
from tenant_schemas.utils import schema_context

from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.util import common as utils
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import PRESTO_LINE_ITEM_TABLE

LOG = logging.getLogger(__name__)


class AzureReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path):
        numeric_columns = [
            "usagequantity",
            "quantity",
            "resourcerate",
            "pretaxcost",
            "costinbillingcurrency",
            "effectiveprice",
            "unitprice",
            "paygprice",
        ]
        date_columns = ["usagedatetime", "date", "billingperiodstartdate", "billingperiodenddate"]
        boolean_columns = ["resource_id_matched"]
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
            parquet_local_path=parquet_local_path,
            column_types=column_types,
            table_name=PRESTO_LINE_ITEM_TABLE,
        )

    @property
    def postgres_summary_table(self):
        """Return the mode for the source specific summary table."""
        return AzureCostEntryLineItemDailySummary

    def create_bill(self, bill_date):
        """Create bill postgres entry."""
        if isinstance(bill_date, str):
            bill_date = ciso8601.parse_datetime(bill_date)
        report_date_range = utils.month_date_range(bill_date)
        start_date, end_date = report_date_range.split("-")

        start_date_utc = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        provider = self._get_provider()

        with schema_context(self._schema_name):
            AzureCostEntryBill.objects.get_or_create(
                billing_period_start=start_date_utc, billing_period_end=end_date_utc, provider=provider
            )
