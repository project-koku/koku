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
from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase


class AWSReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path):
        aws_table_name = f"acct{account}.source_{provider_uuid.replace('-', '_')}_manifest_{manifest_id}"
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
            table_name=aws_table_name,
        )
