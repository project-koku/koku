#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for Parquet files."""
import logging

import prestodb
import pyarrow.parquet as pq
from dateutil.relativedelta import relativedelta
from django.conf import settings
from prestodb.exceptions import PrestoExternalError
from prestodb.exceptions import PrestoQueryError
from prestodb.exceptions import PrestoUserError
from tenant_schemas.utils import schema_context

from api.models import Provider
from masu.util.common import strip_characters_from_column_name
from reporting.models import PartitionedTable

LOG = logging.getLogger(__name__)


class PostgresSummaryTableError(Exception):
    """Postgres summary table is not defined."""


class TrinoExecutionError(Exception):
    """Postgres summary table is not defined."""


class ReportParquetProcessorBase:
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path, column_types, table_name):
        self._manifest_id = manifest_id
        self._account = account
        self._schema_name = f"acct{account}"
        self._parquet_path = parquet_local_path
        self._s3_path = s3_path
        self._provider_uuid = provider_uuid
        self._column_types = column_types
        self._table_name = table_name

    @property
    def postgres_summary_table(self):
        """Return error if unimplemented in subclass."""
        raise PostgresSummaryTableError("This must be a property on the sub class.")

    def _execute_sql(self, sql, schema_name):  # pragma: no cover
        """Execute presto SQL."""
        rows = []
        try:
            with prestodb.dbapi.connect(
                host=settings.PRESTO_HOST, port=settings.PRESTO_PORT, user="admin", catalog="hive", schema=schema_name
            ) as conn:
                cur = conn.cursor()
                cur.execute(sql)
                rows = cur.fetchall()
                LOG.debug(f"_execute_sql rows: {str(rows)}. Type: {type(rows)}")
        except PrestoUserError as err:
            LOG.error(err)
        except (PrestoExternalError, PrestoQueryError) as err:
            LOG.error(err)
            msg = "There was an error running Trino SQL"
            raise TrinoExecutionError(msg)
        return rows

    def _get_provider(self):
        """Retrieve the postgres provider id."""
        return Provider.objects.get(uuid=self._provider_uuid)

    def schema_exists(self):
        """Check if schema exists."""
        schema_check_sql = f"SHOW SCHEMAS LIKE '{self._schema_name}'"
        schema = self._execute_sql(schema_check_sql, "default")
        LOG.info("Checking for schema")
        if schema:
            return True
        return False

    def table_exists(self):
        """Check if table exists."""
        table_check_sql = f"SHOW TABLES LIKE '{self._table_name}'"
        table = self._execute_sql(table_check_sql, self._schema_name)
        LOG.info("Checking for table")
        if table:
            return True
        return False

    def create_schema(self):
        """Create presto schema."""
        schema_create_sql = f"CREATE SCHEMA IF NOT EXISTS {self._schema_name}"
        self._execute_sql(schema_create_sql, "default")
        LOG.info(f"Create Trino/Hive schema SQL: {schema_create_sql}")
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
            norm_col = strip_characters_from_column_name(col)
            if norm_col in self._column_types["numeric_columns"]:
                col_type = "double"
            elif norm_col in self._column_types["date_columns"]:
                col_type = "timestamp"
            elif norm_col in self._column_types["boolean_columns"]:
                col_type = "boolean"
            else:
                col_type = "varchar"

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
        sql = self._generate_create_table_sql()
        self._execute_sql(sql, self._schema_name)
        LOG.info(f"Presto Table: {self._table_name} created.")

    def get_or_create_postgres_partition(self, bill_date, **kwargs):
        """Make sure we have a Postgres partition for a billing period."""
        table_name = self.postgres_summary_table._meta.db_table
        partition_type = kwargs.get("partition_type", PartitionedTable.RANGE)
        partition_column = kwargs.get("partition_column", "usage_start")

        with schema_context(self._schema_name):
            record, created = PartitionedTable.objects.get_or_create(
                schema_name=self._schema_name,
                table_name=f"{table_name}_{bill_date.strftime('%Y_%m')}",
                partition_of_table_name=table_name,
                partition_type=partition_type,
                partition_col=partition_column,
                partition_parameters={
                    "default": False,
                    "from": str(bill_date),
                    "to": str(bill_date + relativedelta(months=1)),
                },
                active=True,
            )
        if created:
            LOG.info(f"Created a new partition for {record.partition_of_table_name} : {record.table_name}")

        return created

    def sync_hive_partitions(self):
        """Sync hive partition metadata for new partitions."""
        LOG.info("Syncing Trino/Hive partitions.")
        sql = f"CALL system.sync_partition_metadata('{self._schema_name}', '{self._table_name}', 'FULL')"
        LOG.info(sql)
        self._execute_sql(sql, self._schema_name)
