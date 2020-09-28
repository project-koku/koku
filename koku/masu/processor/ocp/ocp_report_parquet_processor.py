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
"""Processor for OCP Parquet files."""
import ciso8601
from dateutil import parser
from tenant_schemas.utils import schema_context

from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.util.ocp import common as utils
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import PRESTO_LINE_ITEM_TABLE_MAP


class OCPReportParquetProcessor(ReportParquetProcessorBase):
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path, report_type):
        ocp_table_name = PRESTO_LINE_ITEM_TABLE_MAP[report_type]
        numeric_columns = [
            "pod_usage_cpu_core_seconds",
            "pod_request_cpu_core_seconds",
            "pod_limit_cpu_core_seconds",
            "pod_usage_memory_byte_seconds",
            "pod_request_memory_byte_seconds",
            "pod_limit_memory_byte_seconds",
            "node_capacity_cpu_cores",
            "node_capacity_cpu_core_seconds",
            "node_capacity_memory_bytes",
            "node_capacity_memory_byte_seconds",
            "persistentvolumeclaim_usage_byte_seconds",
            "volume_request_storage_byte_seconds",
            "persistentvolumeclaim_capacity_byte_seconds",
            "persistentvolumeclaim_capacity_bytes",
        ]
        date_columns = ["report_period_start", "report_period_end", "interval_start", "interval_end"]
        json_columns = ["pod_labels"]
        super().__init__(
            manifest_id=manifest_id,
            account=account,
            s3_path=s3_path,
            provider_uuid=provider_uuid,
            parquet_local_path=parquet_local_path,
            numeric_columns=numeric_columns,
            date_columns=date_columns,
            json_columns=json_columns,
            table_name=ocp_table_name,
        )

    def create_bill(self):
        """Create bill postgres entry."""
        sql = f"select distinct(report_period_start), report_period_end from {self._table_name}"
        rows = self._execute_sql(sql, self._schema_name)
        provider = self._get_provider()
        cluster_id = utils.get_cluster_id_from_provider(provider.uuid)
        cluster_alias = utils.get_cluster_alias_from_cluster_id(cluster_id)

        if rows:
            results = rows.pop()
            if results:
                usage_date = results.pop()
                report_date_range = utils.month_date_range(parser.parse(usage_date))
                start_date, end_date = report_date_range.split("-")

                report_period_start = ciso8601.parse_datetime(start_date.replace(" +0000 UTC", "+0000"))
                report_period_end = ciso8601.parse_datetime(end_date.replace(" +0000 UTC", "+0000"))

                with schema_context(self._schema_name):
                    OCPUsageReportPeriod.objects.get_or_create(
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        report_period_start=report_period_start,
                        report_period_end=report_period_end,
                        provider=provider,
                    )
