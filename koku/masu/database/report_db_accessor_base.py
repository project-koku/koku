#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import logging
import os
import time

import ciso8601
import django.apps
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import connection
from django.db import OperationalError
from django.db import transaction
from django_tenants.utils import schema_context
from jinjasql import JinjaSql
from trino.exceptions import TrinoExternalError

import koku.trino_database as trino_db
from api.common import log_json
from api.utils import DateHelper
from koku.database import execute_delete_sql as exec_del_sql
from koku.database_exc import get_extended_exception_by_type
from masu.config import Config
from masu.database.koku_database_access import KokuDBAccess
from masu.database.koku_database_access import mini_transaction_delete
from masu.external.date_accessor import DateAccessor
from reporting.models import PartitionedTable
from reporting_common import REPORT_COLUMN_MAP

LOG = logging.getLogger(__name__)


class ReportDBAccessorException(Exception):
    """An error in the DB accessor."""


class ReportSchema:
    """A container for the reporting table objects."""

    def __init__(self, tables):
        """Initialize the report schema."""
        self.column_types = {}
        self._set_reporting_tables(tables)

    def _set_reporting_tables(self, models):
        """Load table objects for reference and creation.

        Args:
            report_schema (ReportSchema): A schema struct object with all
                report tables
        """
        column_types = {}
        for model in models:
            if "django" in model._meta.db_table:
                continue
            setattr(self, model._meta.db_table, model)
            columns = REPORT_COLUMN_MAP[model._meta.db_table].values()
            types = {column: model._meta.get_field(column).get_internal_type() for column in columns}
            column_types[model._meta.db_table] = types
            self.column_types = column_types


class ReportDBAccessorBase(KokuDBAccess):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self.report_schema = ReportSchema(django.apps.apps.get_models())
        self.trino_prepare_query = JinjaSql(param_style="qmark").prepare_query

        self.date_accessor = DateAccessor()
        self.date_helper = DateHelper()
        self.jinja_sql = JinjaSql()

    @property
    def decimal_precision(self):
        """Return database precision for decimal values."""
        return f"0E-{Config.REPORTING_DECIMAL_PRECISION}"

    @property
    def line_item_daily_summary_table(self):
        """Require this property in subclases."""
        raise ReportDBAccessorException("This must be a property on the sub class.")

    def _get_db_obj_query(self, table, columns=None):
        """Return a query on a specific database table.

        Args:
            table (DjangoModel): Which table to query
            columns (list): A list of column names to exclusively return

        Returns:
            (Query): A query object

        """
        # If table is a str, get the model associated
        if isinstance(table, str):
            table = getattr(self.report_schema, table)

        with schema_context(self.schema):
            if columns:
                query = table.objects.values(*columns)
            else:
                query = table.objects.all()
            return query

    def _execute_raw_sql_query(self, table, sql, start=None, end=None, bind_params=None, operation="UPDATE"):
        """Run a SQL statement via a cursor."""
        if start and end:
            LOG.info("Triggering %s on %s from %s to %s.", operation, table, start, end)
        else:
            LOG.info("Triggering %s %s", operation, table)

        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            try:
                t1 = time.time()
                cursor.execute(sql, params=bind_params)
                t2 = time.time()
            except OperationalError as exc:
                db_exc = get_extended_exception_by_type(exc)
                LOG.error(log_json(os.getpid(), str(db_exc), context=db_exc.as_dict()))
                raise db_exc

        LOG.info("Finished %s on %s in %f seconds.", operation, table, t2 - t1)

    def _execute_trino_raw_sql_query(self, sql, *, sql_params=None, log_ref=None, attempts_left=0):
        """Execute a single trino query returning only the fetchall results"""
        results, _ = self._execute_trino_raw_sql_query_with_description(
            sql, sql_params=sql_params, log_ref=log_ref, attempts_left=attempts_left
        )
        return results

    def _execute_trino_raw_sql_query_with_description(
        self, sql, *, sql_params=None, log_ref="Trino query", attempts_left=0, conn_params=None
    ):
        """Execute a single trino query and return cur.fetchall and cur.description"""
        if sql_params is None:
            sql_params = {}
        if conn_params is None:
            conn_params = {}
        sql, bind_params = self.trino_prepare_query(sql, sql_params)
        t1 = time.time()
        trino_conn = trino_db.connect(schema=self.schema, **conn_params)
        LOG.info(log_json(msg="executing trino sql", log_ref=log_ref, **sql_params))
        try:
            trino_cur = trino_conn.cursor()
            trino_cur.execute(sql, bind_params)
            results = trino_cur.fetchall()
            description = trino_cur.description
        except Exception as ex:
            if attempts_left == 0:
                LOG.error(log_json(msg="failed trino sql execution", log_ref=log_ref, **sql_params), exc_info=ex)
            raise ex
        running_time = time.time() - t1
        LOG.info(log_json(msg="executed trino sql", log_ref=log_ref, running_time=running_time, **sql_params))
        return results, description

    def _execute_trino_multipart_sql_query(self, sql, *, bind_params=None):
        """Execute multiple related SQL queries in Trino."""
        trino_conn = trino_db.connect(schema=self.schema)
        return trino_db.executescript(trino_conn, sql, params=bind_params, preprocessor=self.trino_prepare_query)

    def get_existing_partitions(self, table):
        if isinstance(table, str):
            table_name = table
        else:
            # assume model
            table_name = table._meta.db_table

        with transaction.atomic():  # Make sure this does *not* open a lingering transaction at the driver
            connection.set_schema(self.schema)
            existing_partitions = PartitionedTable.objects.filter(
                schema_name=self.schema, partition_of_table_name=table_name, partition_type=PartitionedTable.RANGE
            ).all()

        return existing_partitions

    def get_partition_start_dates(self, partitions):
        exist_partition_start_dates = {
            ciso8601.parse_datetime(p.partition_parameters["from"]).date()
            for p in partitions
            if not p.partition_parameters["default"]
        }

        return exist_partition_start_dates

    def add_partitions(self, existing_partitions, requested_partition_start_dates):
        tmplpart = existing_partitions[0]
        for needed_partition in {
            r.replace(day=1) for r in requested_partition_start_dates
        } - self.get_partition_start_dates(existing_partitions):
            # This *should* always work as there should always be a default partition
            partition_name = f"{tmplpart.partition_of_table_name}_{needed_partition.strftime('%Y_%m')}"
            # Successfully creating a new record will also create the partition
            newpart_vals = dict(
                schema_name=tmplpart.schema_name,
                table_name=partition_name,
                partition_of_table_name=tmplpart.partition_of_table_name,
                partition_type=tmplpart.partition_type,
                partition_col=tmplpart.partition_col,
                partition_parameters={
                    "default": False,
                    "from": str(needed_partition),
                    "to": str(needed_partition + relativedelta(months=1)),
                },
                active=True,
            )
            self.add_partition(**newpart_vals)

    def add_partition(self, **partition_record):
        with transaction.atomic():
            with schema_context(self.schema):
                newpart, created = PartitionedTable.objects.get_or_create(
                    defaults=partition_record,
                    schema_name=partition_record["schema_name"],
                    table_name=partition_record["table_name"],
                )
        if created:
            LOG.info(f"Created a new partition for {newpart.partition_of_table_name} : {newpart.table_name}")

    def delete_line_item_daily_summary_entries_for_date_range(
        self, source_uuid, start_date, end_date, table=None, filters=None
    ):
        if table is None:
            table = self.line_item_daily_summary_table
        msg = f"Deleting records from {table} from {start_date} to {end_date}"
        LOG.info(msg)
        select_query = table.objects.filter(
            source_uuid=source_uuid, usage_start__gte=start_date, usage_start__lte=end_date
        )
        if filters:
            select_query = select_query.filter(**filters)
        with schema_context(self.schema):
            count, _ = mini_transaction_delete(select_query)
        msg = f"Deleted {count} records from {table}"
        LOG.info(msg)

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

        self._execute_raw_sql_query(table, sql, start_date, end_date, bind_params=filters, operation="DELETE")

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
        table_check_sql = f"SHOW TABLES LIKE '{table_name}'"
        table = self._execute_trino_raw_sql_query(table_check_sql, log_ref="table_exists_trino")
        if table:
            return True
        return False

    def schema_exists_trino(self):
        """Check if table exists."""
        check_sql = f"SHOW SCHEMAS LIKE '{self.schema}'"
        schema_exists = self._execute_trino_raw_sql_query(check_sql, log_ref="schema_exists_trino")
        if schema_exists:
            return True
        return False

    def execute_delete_sql(self, query):
        """
        Detach a partition by marking the active columnm as False in the tracking table
        Schema must be set before this function is called
        Parameters:
            query (QuerySet) : A valid django queryset
        """
        return exec_del_sql(query)

    def delete_hive_partition_by_month(self, table, source, year, month):
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
                    WHERE ocp_source = '{source}'
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
