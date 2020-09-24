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
import logging

import ciso8601
import pytz
from dateutil import parser
from tenant_schemas.utils import schema_context

from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.util import common as utils
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import PRESTO_LINE_ITEM_TABLE

LOG = logging.getLogger(__name__)


class AzureReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path):
        super().__init__(
            manifest_id=manifest_id,
            account=account,
            s3_path=s3_path,
            provider_uuid=provider_uuid,
            parquet_local_path=parquet_local_path,
            numeric_columns=["usagequantity", "resourcerate", "pretaxcost"],
            date_columns=["usagedatetime"],
            table_name=PRESTO_LINE_ITEM_TABLE,
        )

    def create_bill(self):
        """Create bill postgres entry."""
        sql = f"select distinct(usagedatetime) from {self._table_name}"
        rows = self._execute_sql(sql, self._schema_name)
        provider = self._get_provider()
        if rows:
            results = rows.pop()
            if results:
                usage_date = results.pop()
                report_date_range = utils.month_date_range(parser.parse(usage_date))
                start_date, end_date = report_date_range.split("-")

                start_date_utc = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)
                end_date_utc = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, tzinfo=pytz.UTC)

                with schema_context(self._schema_name):
                    AzureCostEntryBill.objects.get_or_create(
                        billing_period_start=start_date_utc, billing_period_end=end_date_utc, provider=provider
                    )
