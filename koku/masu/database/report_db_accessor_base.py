#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import logging
import os
import time

from django.conf import settings
from django.db import connection
from django.db import OperationalError
from django.db import transaction
from jinjasql import JinjaSql
from trino.exceptions import TrinoExternalError

import koku.trino_database as trino_db
from api.common import log_json
from api.utils import DateHelper
from koku.cache import build_trino_schema_exists_key
from koku.cache import build_trino_table_exists_key
from koku.cache import get_value_from_cache
from koku.cache import set_value_in_cache
from koku.database_exc import get_extended_exception_by_type


LOG = logging.getLogger(__name__)


class ReportDBAccessorException(Exception):
    """An error in the DB accessor."""


class ReportDBAccessorBase:
    """Class to interact with customer reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        self.schema = schema

        self.date_helper = DateHelper()
        self.prepare_query = JinjaSql(param_style="format").prepare_query
        self.trino_prepare_query = JinjaSql(param_style="qmark").prepare_query

    def __enter__(self):
        """Enter context manager."""
        connection = transaction.get_connection()
        connection.set_schema(self.schema)
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager reset schema to public and exit."""
        connection = transaction.get_connection()
        connection.set_schema_to_public()

    @property
    def line_item_daily_summary_table(self):
        """Require this property in subclases."""
        raise ReportDBAccessorException("This must be a property on the sub class.")

    @staticmethod
    def extract_context_from_sql_params(sql_params: dict):
        ctx = {}
        if schema := sql_params.get("schema"):
            ctx["schema"] = schema
        if (start := sql_params.get("start")) or (start := sql_params.get("start_date")):
            ctx["start_date"] = start
        if (end := sql_params.get("end")) or (end := sql_params.get("end_date")):
            ctx["end_date"] = end
        if invoice_month := sql_params.get("invoice_month"):
            ctx["invoice_month"] = invoice_month
        if provider_uuid := sql_params.get("source_uuid"):
            ctx["provider_uuid"] = provider_uuid
        if cluster_id := sql_params.get("cluster_id"):
            ctx["cluster_id"] = cluster_id
        return ctx

    def _prepare_and_execute_raw_sql_query(self, table, tmp_sql, tmp_sql_params=None, operation="UPDATE"):
        """Prepare the sql params and run via a cursor."""
        if tmp_sql_params is None:
            tmp_sql_params = {}
        LOG.info(
            log_json(
                msg=f"triggering {operation}",
                table=table,
                context=self.extract_context_from_sql_params(tmp_sql_params),
            )
        )
        sql, sql_params = self.prepare_query(tmp_sql, tmp_sql_params)
        return self._execute_raw_sql_query(table, sql, bind_params=sql_params, operation=operation)

    def _execute_raw_sql_query(self, table, sql, bind_params=None, operation="UPDATE"):
        """Run a SQL statement via a cursor. This also returns a result if the operation is VALIDATION_QUERY."""
        LOG.info(log_json(msg=f"triggering {operation}", table=table))
        row_count = None
        result = None
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            t1 = time.time()
            try:
                cursor.execute(sql, params=bind_params)
                row_count = cursor.rowcount
                if operation == "VALIDATION_QUERY":
                    result = cursor.fetchall()

            except OperationalError as exc:
                db_exc = get_extended_exception_by_type(exc)
                LOG.warning(log_json(os.getpid(), msg=str(db_exc), context=db_exc.as_dict()))
                raise db_exc from exc

        running_time = time.time() - t1
        LOG.info(log_json(msg=f"finished {operation}", row_count=row_count, table=table, running_time=running_time))
        return result

    def _execute_trino_raw_sql_query(self, sql, *, sql_params=None, context=None, log_ref=None, attempts_left=0):
        """Execute a single trino query returning only the fetchall results"""
        results, _ = self._execute_trino_raw_sql_query_with_description(
            sql, sql_params=sql_params, context=context, log_ref=log_ref, attempts_left=attempts_left
        )
        return results

    def _execute_trino_raw_sql_query_with_description(
        self, sql, *, sql_params=None, context=None, log_ref="Trino query", attempts_left=0, conn_params=None
    ):
        """Execute a single trino query and return cur.fetchall and cur.description"""
        if sql_params is None:
            sql_params = {}
        if context is None:
            context = {}
        if conn_params is None:
            conn_params = {}

        if sql_params:
            ctx = self.extract_context_from_sql_params(sql_params)
        elif context:
            ctx = self.extract_context_from_sql_params(context)
        else:
            ctx = {}

        sql, bind_params = self.trino_prepare_query(sql, sql_params)
        t1 = time.time()
        trino_conn = trino_db.connect(schema=self.schema, **conn_params)
        LOG.info(log_json(msg="executing trino sql", log_ref=log_ref, context=ctx))
        try:
            trino_cur = trino_conn.cursor()
            trino_cur.execute(sql, bind_params)
            results = trino_cur.fetchall()
            description = trino_cur.description
        except Exception as ex:
            if attempts_left == 0:
                LOG.error(log_json(msg="failed trino sql execution", log_ref=log_ref, context=ctx), exc_info=ex)
            raise ex
        running_time = time.time() - t1
        LOG.info(log_json(msg="executed trino sql", log_ref=log_ref, running_time=running_time, context=ctx))
        return results, description

    def _execute_trino_multipart_sql_query(self, sql, *, bind_params=None):
        """Execute multiple related SQL queries in Trino."""
        trino_conn = trino_db.connect(schema=self.schema)
        return trino_db.executescript(trino_conn, sql, params=bind_params, preprocessor=self.trino_prepare_query)

    def delete_line_item_daily_summary_entries_for_date_range_raw(
        self, source_uuid, start_date, end_date, filters=None, null_filters=None, table=None
    ):

        if table is None:
            table = self.line_item_daily_summary_table
        if not isinstance(table, str):
            table = table._meta.db_table
        msg = f"Deleting records from {table} for source {source_uuid} from {start_date} to {end_date}"
        LOG.info(msg)

        sql = f"""
            DELETE FROM {self.schema}.{table}
            WHERE usage_start >= %(start_date)s::date
                AND usage_start <= %(end_date)s::date
        """
        if filters:
            filter_list = [f"AND {k} = %({k})s" for k in filters]
            sql += "\n".join(filter_list)
        else:
            filters = {}
        if null_filters:
            filter_list = [f"AND {column} {null_filter}" for column, null_filter in null_filters.items()]
            sql += "\n".join(filter_list)
        filters["start_date"] = start_date
        filters["end_date"] = end_date

        self._execute_raw_sql_query(table, sql, bind_params=filters, operation="DELETE")

    def truncate_partition(self, partition_name):
        """Issue a TRUNCATE command on a specific partition of a table"""
        # Currently all partitions are date based and if the partition does not have YYYY_MM on the end, do not truncate
        year, month = partition_name.split("_")[-2:]
        try:
            int(year)
            int(month)
        except ValueError:
            msg = "Invalid paritition provided. No TRUNCATE performed."
            LOG.warning(msg)
            return

        sql = f"""
            DO $$
            BEGIN
            IF exists(
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = '{self.schema}'
                    AND table_name='{partition_name}'
            )
            THEN
                TRUNCATE {self.schema}.{partition_name};
            END IF;
            END $$;
        """
        self._execute_raw_sql_query(partition_name, sql, operation="TRUNCATE")

    def table_exists_trino(self, table_name):
        """Check if table exists."""
        cache_key = build_trino_table_exists_key(self.schema, table_name)
        if result := get_value_from_cache(cache_key):
            return result
        table_check_sql = f"SHOW TABLES LIKE '{table_name}'"
        exists = bool(self._execute_trino_raw_sql_query(table_check_sql, log_ref="table_exists_trino"))
        set_value_in_cache(cache_key, exists)
        return exists

    def schema_exists_trino(self):
        """Check if table exists."""
        cache_key = build_trino_schema_exists_key(self.schema)
        if result := get_value_from_cache(cache_key):
            return result
        check_sql = f"SHOW SCHEMAS LIKE '{self.schema}'"
        exists = bool(self._execute_trino_raw_sql_query(check_sql, log_ref="schema_exists_trino"))
        set_value_in_cache(cache_key, exists)
        return exists

    def delete_hive_partition_by_month(self, table, source, year, month, source_column="ocp_source"):
        """Deletes partitions individually by month."""
        retries = settings.HIVE_PARTITION_DELETE_RETRIES
        if self.schema_exists_trino() and self.table_exists_trino(table):
            LOG.info(
                "Deleting Hive partitions for the following: \n\tSchema: %s "
                "\n\tOCP Source: %s \n\tTable: %s \n\tYear: %s \n\tMonths: %s",
                self.schema,
                source,
                table,
                year,
                month,
            )
            for i in range(retries):
                try:
                    sql = f"""
                    DELETE FROM hive.{self.schema}.{table}
                    WHERE {source_column} = '{source}'
                    AND year = '{year}'
                    AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
                    """
                    self._execute_trino_raw_sql_query(
                        sql,
                        log_ref=f"delete_hive_partition_by_month for {year}-{month}",
                        attempts_left=(retries - 1) - i,
                    )
                    break
                except TrinoExternalError as err:
                    if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                        continue
                    else:
                        raise err
