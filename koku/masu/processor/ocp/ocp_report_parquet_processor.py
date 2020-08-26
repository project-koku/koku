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
import logging

import prestodb
import pyarrow.parquet as pq
from django.conf import settings

LOG = logging.getLogger(__name__)


class OCPReportParquetProcessor:
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path, report_type):
        self._manifest_id = manifest_id
        self._account = account
        self._schema_name = f"acct{account}"
        self._parquet_path = parquet_local_path
        self._s3_path = s3_path
        self._provider_uuid = provider_uuid
        self._report_type = report_type

    def _execute_sql(self, sql, schema_name):
        """Execute presto SQL."""
        conn = prestodb.dbapi.connect(
            host=settings.PRESTO_HOST, port=settings.PRESTO_PORT, user="admin", catalog="hive", schema=schema_name
        )
        cur = conn.cursor()
        cur.execute(sql)
        cur.fetchall()
        conn.close()

    def _create_schema(self,):
        """Create presto schema."""
        schema_create_sql = f"CREATE SCHEMA IF NOT EXISTS {self._schema_name}"
        self._execute_sql(schema_create_sql, "default")
        return self._schema_name

    def _generate_column_list(self):
        """Generate column list based on parquet file."""
        parquet_file = self._parquet_path
        table = pq.read_table(parquet_file)
        return table.column_names

    def _generate_create_table_sql(self):
        """Generate SQL to create table."""
        parquet_columns = self._generate_column_list()
        s3_path = f"{settings.S3_BUCKET_NAME}/{self._s3_path}"

        table_name = (
            f"{self._schema_name}.source_{self._provider_uuid.replace('-', '_')}"
            f"_type_{self._report_type}_manifest_{self._manifest_id}"
        )
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ("

        for idx, col in enumerate(parquet_columns):
            norm_col = col.replace("/", "_").replace(":", "_").lower()
            col_type = "varchar"
            if norm_col in [
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
            ]:
                col_type = "double"
            if norm_col in ["report_period_start", "report_period_end", "interval_start", "interval_end"]:
                col_type = "timestamp"
            sql += f"{norm_col} {col_type}"
            if idx < (len(parquet_columns) - 1):
                sql += ","

        sql += f") WITH(external_location = 's3a://{s3_path}', format = 'PARQUET')"
        LOG.debug(f"Create Parquet Table SQL: {sql}")
        return sql, table_name

    def create_table(self):
        """Create presto SQL table."""
        schema = self._create_schema()
        sql, table_name = self._generate_create_table_sql()
        self._execute_sql(sql, schema)
        LOG.info(f"Presto Table: {table_name} created.")
