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
"""Processor for Parquet files."""
import logging

import prestodb
import pyarrow.parquet as pq
from django.conf import settings
from tenant_schemas.utils import schema_context

from api.models import Provider

LOG = logging.getLogger(__name__)


class ReportParquetProcessorBase:
    def __init__(
        self,
        manifest_id,
        account,
        s3_path,
        provider_uuid,
        parquet_local_path,
        numeric_columns,
        date_columns,
        table_name,
    ):
        self._manifest_id = manifest_id
        self._account = account
        self._schema_name = f"acct{account}"
        self._parquet_path = parquet_local_path
        self._s3_path = s3_path
        self._provider_uuid = provider_uuid
        self._numeric_columns = numeric_columns
        self._date_columns = date_columns
        self._table_name = table_name

    def _execute_sql(self, sql, schema_name):  # pragma: no cover
        """Execute presto SQL."""
        with prestodb.dbapi.connect(
            host=settings.PRESTO_HOST, port=settings.PRESTO_PORT, user="admin", catalog="hive", schema=schema_name
        ) as conn:
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
            LOG.debug(f"_execute_sql rows: {str(rows)}. Type: {type(rows)}")
        return rows

    def _get_provider(self):
        """Retrieve the postgres provider id."""
        with schema_context(self._schema_name):
            obj = Provider.objects.get(uuid=self._provider_uuid)
            return obj
        return None

    def _create_schema(self,):
        """Create presto schema."""
        schema_create_sql = f"CREATE SCHEMA IF NOT EXISTS {self._schema_name}"
        self._execute_sql(schema_create_sql, "default")
        return self._schema_name

    def _generate_column_list(self):
        """Generate column list based on parquet file."""
        parquet_file = self._parquet_path
        return pq.ParquetFile(parquet_file).schema.names

    def _generate_create_table_sql(self):
        """Generate SQL to create table."""
        parquet_columns = self._generate_column_list()
        s3_path = f"{settings.S3_BUCKET_NAME}/{self._s3_path}"

        sql = f"CREATE TABLE IF NOT EXISTS {self._schema_name}.{self._table_name} ("

        for idx, col in enumerate(parquet_columns):
            norm_col = col.replace("/", "_").replace(":", "_").lower()
            col_type = "varchar"
            if norm_col in self._numeric_columns:
                col_type = "double"
            if norm_col in self._date_columns:
                col_type = "timestamp"
            sql += f"{norm_col} {col_type}"
            if idx < (len(parquet_columns) - 1):
                sql += ","
        sql += ",source varchar, year varchar, month varchar"

        sql += (
            f") WITH(external_location = 's3a://{s3_path}', format = 'PARQUET',"
            " partitioned_by=ARRAY['source', 'year', 'month'])"
        )
        LOG.info(f"Create Parquet Table SQL: {sql}")
        return sql

    def create_table(self):
        """Create presto SQL table."""
        schema = self._create_schema()
        sql = self._generate_create_table_sql()
        self._execute_sql(sql, schema)

        sql = f"CALL system.sync_partition_metadata('{self._schema_name}', '{self._table_name}', 'FULL')"
        LOG.info(sql)
        self._execute_sql(sql, schema)

        LOG.info(f"Presto Table: {self._table_name} created.")
