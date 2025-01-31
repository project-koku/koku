#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for Parquet files."""
import logging

import pyarrow.parquet as pq
import trino
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django_tenants.utils import schema_context
from trino.exceptions import TrinoExternalError
from trino.exceptions import TrinoQueryError
from trino.exceptions import TrinoUserError

from api.common import log_json
from api.models import Provider
from koku.cache import build_trino_schema_exists_key
from koku.cache import build_trino_table_exists_key
from koku.cache import get_value_from_cache
from koku.cache import set_value_in_cache
from koku.pg_partition import get_or_create_partition
from masu.util.common import strip_characters_from_column_name
from reporting.models import PartitionedTable
from reporting.models import TenantAPIProvider

LOG = logging.getLogger(__name__)


class PostgresSummaryTableError(Exception):
    """Postgres summary table is not defined."""


class ReportParquetProcessorBase:
    def __init__(self, manifest_id, account, s3_path, provider_uuid, parquet_local_path, column_types, table_name):
        self._manifest_id = manifest_id
        self._account = account
        # Existing schema will start with acct and we strip that prefix for use later
        # new customers include the org prefix in case an org-id and an account number might overlap
        if account.startswith("org"):
            self._schema_name = str(account)
        else:
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

    def _execute_trino_sql(self, sql, schema_name: str):  # pragma: no cover
        """Execute Trino SQL."""
        rows = []
        try:
            with trino.dbapi.connect(
                host=settings.TRINO_HOST, port=settings.TRINO_PORT, user="admin", catalog="hive", schema=schema_name
            ) as conn:
                cur = conn.cursor()
                cur.execute(sql)
                rows = cur.fetchall()
                LOG.debug(f"_execute_trino_sql rows: {str(rows)}. Type: {type(rows)}")
        except TrinoUserError as err:
            LOG.warning(err)
        except TrinoExternalError as err:
            if err.error_name in ("HIVE_METASTORE_ERROR", "HIVE_FILESYSTEM_ERROR", "JDBC_ERROR"):
                LOG.warning(err)
            else:
                LOG.error(err)
        except TrinoQueryError as err:
            LOG.error(err)

        return rows

    def _get_provider(self):
        """Retrieve the postgres provider id."""
        return Provider.objects.get(uuid=self._provider_uuid)

    def _get_tenant_provider(self):
        """Retrieve the postgres provider id."""
        with schema_context(self._account):
            return TenantAPIProvider.objects.get(uuid=self._provider_uuid)

    def schema_exists(self):
        """Check if schema exists."""
        LOG.info(log_json(msg="checking for schema", schema=self._schema_name))
        cache_key = build_trino_schema_exists_key(self._schema_name)
        if result := get_value_from_cache(cache_key):
            return result
        schema_check_sql = f"SHOW SCHEMAS LIKE '{self._schema_name}'"
        exists = bool(self._execute_trino_sql(schema_check_sql, "default"))
        set_value_in_cache(cache_key, exists)
        return exists

    def table_exists(self):
        """Check if table exists."""
        LOG.info(log_json(msg="checking for table", table=self._table_name, schema=self._schema_name))
        cache_key = build_trino_table_exists_key(self._schema_name, self._table_name)
        if result := get_value_from_cache(cache_key):
            return result
        table_check_sql = f"SHOW TABLES LIKE '{self._table_name}'"
        exists = bool(self._execute_trino_sql(table_check_sql, self._schema_name))
        set_value_in_cache(cache_key, exists)
        return exists

    def create_schema(self):
        """Create Trino schema."""
        LOG.info(log_json(msg="create trino/hive schema sql", schema=self._schema_name))
        schema_create_sql = f"CREATE SCHEMA IF NOT EXISTS {self._schema_name}"
        self._execute_trino_sql(schema_create_sql, "default")
        return self._schema_name

    def _generate_column_list(self):
        """Generate column list based on parquet file."""
        parquet_file = self._parquet_path
        return pq.ParquetFile(parquet_file).schema.names

    def _generate_create_table_sql(self, partition_map=None):
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
        if partition_map:
            # Add the specified partition columns
            sql += ", "
            sql += ",".join([f"{item[0]} {item[1]} " for item in list(partition_map.items())])
            partition_column_str = ", ".join([f"'{key}'" for key in partition_map.keys()])
            sql += (
                f") WITH(external_location = '{settings.TRINO_S3A_OR_S3}://{s3_path}', format = 'PARQUET',"
                f" partitioned_by=ARRAY[{partition_column_str}])"
            )
        else:
            # Use the default partition columns
            sql += ",source varchar, year varchar, month varchar"

            sql += (
                f") WITH(external_location = '{settings.TRINO_S3A_OR_S3}://{s3_path}', format = 'PARQUET',"
                " partitioned_by=ARRAY['source', 'year', 'month'])"
            )
        return sql

    def create_table(self, partition_map=None):
        """Create Trino SQL table."""
        sql = self._generate_create_table_sql(partition_map=partition_map)
        LOG.info(log_json(msg="attempting to create parquet table", table=self._table_name, schema=self._schema_name))
        self._execute_trino_sql(sql, self._schema_name)
        LOG.info(log_json(msg="trino parquet table created", table=self._table_name, schema=self._schema_name))

    def get_or_create_postgres_partition(self, bill_date, **kwargs):
        """Make sure we have a Postgres partition for a billing period."""
        table_name = self.postgres_summary_table._meta.db_table
        partition_type = kwargs.get("partition_type", PartitionedTable.RANGE)
        partition_column = kwargs.get("partition_column", "usage_start")

        # Get or Create records for last partition, this partition, next partition range
        # This is to help with those vendors whose billing info spills over a 1-month
        # boundary. The next boundary partition will be created in case of a reprocess.
        _bill_date = bill_date.replace(day=1)  # Force a month-start bounds
        one_month_delta = relativedelta(months=1)
        two_month_delta = relativedelta(months=2)
        partition_ranges = (
            (_bill_date - one_month_delta, _bill_date),
            (_bill_date, _bill_date + one_month_delta),
            (_bill_date + one_month_delta, _bill_date + two_month_delta),
        )

        part_rec = dict(
            schema_name=self._schema_name,
            table_name=None,
            partition_of_table_name=table_name,
            partition_type=partition_type,
            partition_col=partition_column,
            partition_parameters={"default": False, "from": None, "to": None},
            active=True,
        )

        created = False  # used for actual bill_date partition
        for _from, _to in partition_ranges:
            part_rec["table_name"] = f'{table_name}_{_from.strftime("%Y_%m")}'
            part_rec["partition_parameters"]["from"] = str(_from)
            part_rec["partition_parameters"]["to"] = str(_to)
            # This func will to the get_or_create on the tracking table
            # which, if needed, will fire the trigger to create a partition
            # BUT it will also check the default partition for overlapping data
            # AND move it to the new partition.
            record, _created = get_or_create_partition(part_rec)
            if _from == _bill_date:
                created = _created
            if _created:
                LOG.info(
                    log_json(
                        msg="created a new partition",
                        schema=self._schema_name,
                        table=record.partition_of_table_name,
                        partition=record.table_name,
                    )
                )

        return created

    def sync_hive_partitions(self):
        """Sync hive partition metadata for new partitions."""
        LOG.info(
            log_json(
                msg="syncing trino/hive partitions",
                schema=self._schema_name,
                table=self._table_name,
            )
        )
        sql = "CALL system.sync_partition_metadata('" f"{self._schema_name}', " f"'{self._table_name}', " "'FULL')"
        LOG.info(sql)
        self._execute_trino_sql(sql, self._schema_name)
