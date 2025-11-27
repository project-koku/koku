#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for Parquet files."""
import base64
import hashlib
import logging

import pyarrow.parquet as pq
from koku.reportdb_accessor import ColumnType, get_report_db_accessor
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django_tenants.utils import schema_context
from trino.exceptions import TrinoQueryError
from trino.exceptions import TrinoUserError
from django.db import ProgrammingError, Error
from sqlalchemy import create_engine

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
    def __init__(self, manifest_id, account, s3_path, provider_uuid, column_types, table_name, start_date):
        self._manifest_id = manifest_id
        self._account = account
        # Existing schema will start with acct and we strip that prefix for use later
        # new customers include the org prefix in case an org-id and an account number might overlap
        if account.startswith("org"):
            self._schema_name = str(account)
        else:
            self._schema_name = f"acct{account}"
        self._s3_path = s3_path
        self._provider_uuid = provider_uuid
        self._column_types = column_types
        self._table_name = table_name
        self._year = start_date.strftime("%Y")
        self._month = start_date.strftime("%m")
        self._partition_name = self._create_partition_name(self._year, self._month)
    @property
    def postgres_summary_table(self):
        """Return error if unimplemented in subclass."""
        raise PostgresSummaryTableError("This must be a property on the sub class.")

    def _execute_trino_sql(self, sql, schema_name: str):  # pragma: no cover
        """Execute Trino SQL."""
        rows = []
        with get_report_db_accessor().connect(
            host=settings.TRINO_HOST, port=settings.TRINO_PORT, user="admin", catalog="hive", schema=schema_name
        ) as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(sql)
                    rows = cur.fetchall()
                    LOG.debug(f"_execute_trino_sql rows: {str(rows)}. Type: {type(rows)}")
                except ProgrammingError as err:
                    LOG.warning(err)
                except TrinoQueryError as err:
                    if err.error_name in ("HIVE_METASTORE_ERROR", "HIVE_FILESYSTEM_ERROR", "JDBC_ERROR"):
                        LOG.warning(err)
                    else:
                        LOG.error(err)
                except Error as err: # TrinoQueryError is the equivalent of Error in Django
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
        schema_check_sql = get_report_db_accessor().get_schema_check_sql(self._schema_name)
        exists = bool(self._execute_trino_sql(schema_check_sql, "default"))
        set_value_in_cache(cache_key, exists)
        return exists

    def table_exists(self):
        """Check if table exists."""
        LOG.info(log_json(msg="checking for table", table=self._table_name, schema=self._schema_name))
        cache_key = build_trino_table_exists_key(self._schema_name, self._table_name)
        if result := get_value_from_cache(cache_key):
            return result
        table_check_sql = get_report_db_accessor().get_table_check_sql(self._table_name, self._schema_name)
        exists = bool(self._execute_trino_sql(table_check_sql, self._schema_name))
        set_value_in_cache(cache_key, exists)
        return exists

    def create_schema(self):
        """Create Trino schema."""
        LOG.info(log_json(msg="create trino/hive schema sql", schema=self._schema_name))
        schema_create_sql = get_report_db_accessor().get_schema_create_sql(self._schema_name)
        self._execute_trino_sql(schema_create_sql, "default")
        return self._schema_name

    def _generate_create_table_sql(self, column_names):
        """Generate SQL to create table."""
        columns = []
        for col in column_names:
            norm_col = strip_characters_from_column_name(col)
            if norm_col in self._column_types["numeric_columns"]:
                column_type = ColumnType.NUMERIC
            elif norm_col in self._column_types["date_columns"]:
                column_type = ColumnType.DATE
            elif norm_col in self._column_types["boolean_columns"]:
                column_type = ColumnType.BOOLEAN
            else:
                column_type = ColumnType.STRING
            columns.append((norm_col, column_type))

        partition_columns = [("source", ColumnType.STRING), ("year", ColumnType.STRING), ("month", ColumnType.STRING)]
        
        sql = get_report_db_accessor().get_table_create_sql(self._table_name, self._schema_name, columns, partition_columns, self._s3_path)
        
        return sql

    def create_table(self, column_names):
        """Create Trino SQL table."""
        sql = self._generate_create_table_sql(column_names)
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

    def write_dataframe_to_sql(self, data_frame):
        """Write dataframe to sql."""
        with get_report_db_accessor().connect() as connection:
            engine = create_engine('postgresql://',creator=lambda: connection.getConnection())
            #
            # Add values for partition columns
            # Write to partition directly for performance
            #
            data_frame['year'] = self._year
            data_frame['month'] = self._month
            data_frame['source'] = self._provider_uuid
            data_frame.to_sql(self._partition_name, engine, self._schema_name, if_exists='append', index=False)

    def _create_partition_name(self, year, month):
        """Create a unique partition name.
        In Postgres the partition is a table. Its name is limited to 63 chars including schema. The table name with the partition values require more chars. Thereofore, we need some other unique identifier.
        The name is a base64 encoded sha256 hash of the table name, provider uuid, year, and month.
        """
        value = f"{self._table_name}{self._provider_uuid}{year}{month}"
        hash = hashlib.sha256(value.encode('ascii')).digest()
        b64value = base64.b64encode(hash).decode('ascii')
        return b64value
    
    def create_report_partition(self):
        partition_values_lower = [f"'{self._provider_uuid}'", f"'{self._year}'", f"'{self._month}'"]
        partition_values_upper = [f"'{self._provider_uuid}'", f"'{self._year}'", f"'{int(self._month)+1:02d}'"]
        sql = get_report_db_accessor().get_partition_create_sql(self._schema_name, self._table_name, self._partition_name, partition_values_lower, partition_values_upper)
        self._execute_trino_sql(sql, self._schema_name)