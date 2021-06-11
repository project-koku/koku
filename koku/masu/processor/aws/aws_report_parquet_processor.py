#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for AWS Parquet files."""
import ciso8601
import pytz
from tenant_schemas.utils import schema_context

from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.util import common as utils
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import PRESTO_LINE_ITEM_TABLE


class AWSReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path):
        numeric_columns = [
            "lineitem_normalizationfactor",
            "lineitem_normalizedusageamount",
            "lineitem_usageamount",
            "lineitem_unblendedcost",
            "lineitem_unblendedrate",
            "lineitem_blendedcost",
            "lineitem_blendedrate",
            "pricing_publicondemandrate",
            "pricing_publicondemandcost",
        ]
        date_columns = [
            "lineitem_usagestartdate",
            "lineitem_usageenddate",
            "bill_billingperiodstartdate",
            "bill_billingperiodenddate",
        ]
        super().__init__(
            manifest_id=manifest_id,
            account=account,
            s3_path=s3_path,
            provider_uuid=provider_uuid,
            parquet_local_path=parquet_local_path,
            numeric_columns=numeric_columns,
            date_columns=date_columns,
            table_name=PRESTO_LINE_ITEM_TABLE,
        )

    @property
    def postgres_summary_table(self):
        """Return the mode for the source specific summary table."""
        return AWSCostEntryLineItemDailySummary

    def create_bill(self, bill_date):
        """Create bill postgres entry."""
        if isinstance(bill_date, str):
            bill_date = ciso8601.parse_datetime(bill_date)
        report_date_range = utils.month_date_range(bill_date)
        start_date, end_date = report_date_range.split("-")

        start_date_utc = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
        end_date_utc = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

        sql = f"""
            SELECT DISTINCT bill_payeraccountid
            FROM {self._table_name}
            WHERE source = '{self._provider_uuid}'
                AND year = '{bill_date.strftime("%Y")}'
                AND month = '{bill_date.strftime("%m")}'
        """

        rows = self._execute_sql(sql, self._schema_name)
        payer_account_id = None
        if rows:
            payer_account_id = rows[0][0]

        provider = self._get_provider()

        with schema_context(self._schema_name):
            AWSCostEntryBill.objects.get_or_create(
                billing_period_start=start_date_utc,
                billing_period_end=end_date_utc,
                payer_account_id=payer_account_id,
                provider=provider,
            )
