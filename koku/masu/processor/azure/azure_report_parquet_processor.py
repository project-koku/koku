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
"""Processor for Azure Parquet files."""
from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase


class AzureReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path):
        azure_table_name = f"acct{account}.source_{provider_uuid.replace('-', '_')}_manifest_{manifest_id}"
        super().__init__(
            manifest_id=manifest_id,
            account=account,
            s3_path=s3_path,
            provider_uuid=provider_uuid,
            parquet_local_path=parquet_local_path,
            numeric_columns=["usagequantity", "resourcerate", "pretaxcost"],
            date_columns=["usagedatetime"],
            table_name=azure_table_name,
        )
