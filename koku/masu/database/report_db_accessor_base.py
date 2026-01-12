#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import logging
import os
import pkgutil
import time
from typing import Any

from django.conf import settings
from django.db import connection
from django.db import OperationalError
from django.db import transaction
from django.db.utils import ProgrammingError as DjangoProgrammingError
from jinjasql import JinjaSql
from trino.exceptions import TrinoExternalError
from trino.exceptions import TrinoQueryError

import koku.trino_database as trino_db
from api.common import log_json
from api.utils import DateHelper
from koku.cache import build_trino_schema_exists_key
from koku.cache import build_trino_table_exists_key
from koku.cache import get_value_from_cache
from koku.cache import set_value_in_cache
from koku.database_exc import get_extended_exception_by_type
from koku.reportdb_accessor import get_report_db_accessor
from koku.trino_database import extract_context_from_sql_params
from koku.trino_database import retry
from koku.trino_database import TrinoHiveMetastoreError
from koku.trino_database import TrinoNoSuchKeyError
from masu.processor.parquet.summary_sql_metadata import SummarySqlMetadata

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
        self.prepare_query = JinjaSql(param_style="pyformat").prepare_query
        param_style = get_report_db_accessor().get_bind_param_style()
        self.trino_prepare_query = JinjaSql(param_style=param_style).prepare_query

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
        return extract_context_from_sql_params(sql_params)

    def get_sql_folder_name(self):
        """Return the SQL folder name based on ONPREM setting.

        Returns:
            str: 'postgres_sql' if ONPREM is True, otherwise 'trino_sql'
        """
        return "postgres_sql" if getattr(settings, "ONPREM", False) else "trino_sql"

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

    def _execute_trino_raw_sql_query(self, sql, *, sql_params=None, context=None, log_ref=None):
        """Execute a single trino query returning only the fetchall results"""
        if sql_params is None:
            sql_params = {}
        results, _ = self._execute_trino_raw_sql_query_with_description(
            sql, sql_params=sql_params, context=context, log_ref=log_ref
        )
        return results

    @retry(retry_on=(TrinoNoSuchKeyError, TrinoHiveMetastoreError))
    def _execute_trino_raw_sql_query_with_description(
        self,
        sql,
        *,
        sql_params: dict,
        context=None,
        log_ref="Trino query",
        conn_params=None,
    ):
        """Execute a single trino query and return cur.fetchall and cur.description"""
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
            try:
                results = trino_cur.fetchall()
            except DjangoProgrammingError as e:
                # PostgreSQL raises "no results to fetch" for CREATE/DROP without RETURNING
                if "no results to fetch" in str(e):
                    results = []
                else:
                    raise
            description = trino_cur.description
        except TrinoQueryError as ex:
            if "NoSuchKey" in str(ex):
                raise TrinoNoSuchKeyError(
                    message=ex.message,
                    query_id=ex.query_id,
                    error_code=ex.error_code,
                )

            if ex.error_name == "HIVE_METASTORE_ERROR":
                raise TrinoHiveMetastoreError(
                    message=ex.message,
                    query_id=ex.query_id,
                    error_code=ex.error_code,
                )

            raise
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

        filters = filters or {}  # convert None -> dict
        null_filters = null_filters or {}  # convert None -> dict

        tmp_sql = """
            DELETE FROM {{schema | sqlsafe}}.{{table | sqlsafe}}
                WHERE usage_start >= {{start_date}}
                AND usage_start <= {{end_date}}
                {% for k, v in filters.items() -%}
                    AND {{ k | sqlsafe }} = {{ v }}
                {% endfor -%}
                {% for k, v in null_filters.items() -%}
                    AND {{ k | sqlsafe }} {{ v | sqlsafe }}
                {% endfor -%}
        """
        tmp_sql_params = {
            "schema": self.schema,
            "table": table,
            "start_date": start_date,
            "end_date": end_date,
            "filters": filters,
            "null_filters": null_filters,
        }
        self._prepare_and_execute_raw_sql_query(table, tmp_sql, tmp_sql_params, operation="DELETE")

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
        table_check_sql = get_report_db_accessor().get_table_check_sql(table_name, self.schema)
        exists = bool(self._execute_trino_raw_sql_query(table_check_sql, log_ref="table_exists_trino"))
        set_value_in_cache(cache_key, exists)
        return exists

    def schema_exists_trino(self):
        """Check if table exists."""
        cache_key = build_trino_schema_exists_key(self.schema)
        if result := get_value_from_cache(cache_key):
            return result
        check_sql = get_report_db_accessor().get_schema_check_sql(self.schema)
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
                    sql = get_report_db_accessor().get_delete_by_month_sql(
                        schema_name=self.schema,
                        table_name=table,
                        source_column=source_column,
                        source=source,
                        year=year,
                        month=month,
                    )
                    self._execute_trino_raw_sql_query(
                        sql,
                        log_ref=f"delete_hive_partition_by_month for {year}-{month}",
                    )
                    break
                except TrinoExternalError as err:
                    if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                        continue
                    else:
                        raise err
                except OperationalError as err:
                    if i < (retries - 1):
                        continue
                    else:
                        raise err

    def find_openshift_keys_expected_values(self, sql_metadata: SummarySqlMetadata) -> Any:
        """
        We need to find the expected values for the openshift specific keys.
        Keys: openshift-project, openshift-node, openshift-cluster
        Ex: ("openshift-project": "project_a")
        """
        matched_tag_params = sql_metadata.build_params(
            ["schema", "start_date", "end_date", "month", "year", "matched_tag_strs", "ocp_provider_uuid"]
        )
        matched_tags_sql = pkgutil.get_data(
            "masu.database", f"{self.get_sql_folder_name()}/openshift/ocp_special_matched_tags.sql"
        )
        matched_tags_sql = matched_tags_sql.decode("utf-8")
        LOG.info(log_json(msg="Finding expected values for openshift special tags", **matched_tag_params))
        matched_tags_result = self._execute_trino_multipart_sql_query(matched_tags_sql, bind_params=matched_tag_params)
        return matched_tags_result[0][0]
