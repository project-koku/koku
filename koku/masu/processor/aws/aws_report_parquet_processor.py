#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Processor for AWS Parquet files."""
from tenant_schemas.utils import schema_context

from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
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

    def create_bill(self):
        """Create bill postgres entry."""
        sql = (
            f"select distinct(bill_billingperiodstartdate), bill_billingperiodenddate, "
            f"bill_billtype, bill_payeraccountid from {self._table_name}"
        )
        rows = self._execute_sql(sql, self._schema_name)
        provider = self._get_provider()
        if rows:
            results = rows.pop()
            start_date, end_date, bill_type, payer_account_id = results
            with schema_context(self._schema_name):
                AWSCostEntryBill.objects.get_or_create(
                    bill_type=bill_type,
                    billing_period_start=start_date,
                    billing_period_end=end_date,
                    payer_account_id=payer_account_id,
                    provider=provider,
                )
