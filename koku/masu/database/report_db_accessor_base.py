#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for report data."""
import logging
import os
import uuid
from decimal import Decimal
from decimal import InvalidOperation

import ciso8601
import django.apps
from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db import OperationalError
from django.db import transaction
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context

import koku.presto_database as kpdb
from api.common import log_json
from koku.database import execute_delete_sql as exec_del_sql
from koku.database_exc import get_extended_exception_by_type
from masu.config import Config
from masu.database.koku_database_access import KokuDBAccess
from masu.database.koku_database_access import mini_transaction_delete
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
            column_types.update({model._meta.db_table: types})
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

    @property
    def decimal_precision(self):
        """Return database precision for decimal values."""
        return f"0E-{Config.REPORTING_DECIMAL_PRECISION}"

    @property
    def line_item_daily_summary_table(self):
        """Require this property in subclases."""
        raise ReportDBAccessorException("This must be a property on the sub class.")

    def create_temp_table(self, table_name, drop_column=None):
        """Create a temporary table and return the table name."""
        temp_table_name = table_name + "_" + str(uuid.uuid4()).replace("-", "_")
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(f"CREATE TEMPORARY TABLE {temp_table_name} (LIKE {table_name})")
            if drop_column:
                cursor.execute(f"ALTER TABLE {temp_table_name} DROP COLUMN {drop_column}")
        return temp_table_name

    def create_new_temp_table(self, table_name, columns):
        """Create a temporary table and return the table name."""
        temp_table_name = table_name + "_" + str(uuid.uuid4()).replace("-", "_")
        base_sql = f"CREATE TEMPORARY TABLE {temp_table_name} "
        column_types = ""
        for column in columns:
            for name, column_type in column.items():
                column_types += f"{name} {column_type}, "
        column_types = column_types.strip().rstrip(",")
        column_sql = f"({column_types})"
        table_sql = base_sql + column_sql
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(table_sql)

        return temp_table_name

    def merge_temp_table(self, table_name, temp_table_name, columns, conflict_columns=None):
        """INSERT temp table rows into the primary table specified.

        Args:
            table_name (str): The main table to insert into
            temp_table_name (str): The temp table to pull from
            columns (list): A list of columns to use in the insert logic

        Returns:
            (None)

        """
        column_str = ",".join(columns)
        upsert_sql = f"""
            INSERT INTO {table_name} ({column_str})
                SELECT {column_str}
                FROM {temp_table_name}
            """

        if conflict_columns:
            conflict_col_str = ",".join(conflict_columns)
            set_clause = ",".join([f"{column} = excluded.{column}" for column in columns])
            conflict_sql = f"""
                    ON CONFLICT ({conflict_col_str}) DO UPDATE
                    SET {set_clause}
                """
            upsert_sql += conflict_sql

        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(upsert_sql)

            delete_sql = f"DELETE FROM {temp_table_name}"
            cursor.execute(delete_sql)

    def bulk_insert_rows(self, file_obj, table, columns, sep=","):
        """Insert many rows using Postgres copy functionality.

        Args:
            file_obj (file): A file-like object containing CSV rows
            table (str): The table name in the databse to copy to
            columns (list): A list of columns in the order of the CSV file
            sep (str): The separator in the file. Default: ','

        """
        columns = ", ".join(columns)
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            statement = f"COPY {table} ({columns}) FROM STDIN WITH CSV DELIMITER '{sep}'"
            cursor.copy_expert(statement, file_obj)

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

    def create_db_object(self, table_name, data):
        """Instantiate a populated database object.

        Args:
            table_name (str): The name of the table to create
            data (dict): A dictionary of data to insert into the object

        Returns:
            (Table): A populated SQLAlchemy table object specified by table_name

        """
        table = getattr(self.report_schema, table_name)
        data = self.clean_data(data, table_name)

        with schema_context(self.schema):
            model_object = table(**data)
            model_object.save()
            return model_object

    def insert_on_conflict_do_nothing(self, table, data, conflict_columns=None):
        """Write an INSERT statement with an ON CONFLICT clause.

        This is useful to avoid duplicate row inserts. Intended for
        single row inserts.

        Args:
            table_name (str): The name of the table to insert into
            data (dict): A dictionary of data to insert into the object
            columns (list): A list of columns to check conflict on

        Returns:
            (str): The id of the inserted row

        """
        table_name = table()._meta.db_table
        data = self.clean_data(data, table_name)
        columns_formatted = ", ".join(str(value) for value in data.keys())
        values = list(data.values())
        val_str = ",".join(["%s" for _ in data])
        insert_sql = f"""
            INSERT INTO {self.schema}.{table_name}({columns_formatted}) VALUES({val_str})
            """
        if conflict_columns:
            conflict_columns_formatted = ", ".join(conflict_columns)
            insert_sql = insert_sql + f" ON CONFLICT ({conflict_columns_formatted}) DO NOTHING;"
        else:
            insert_sql = insert_sql + " ON CONFLICT DO NOTHING;"
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(insert_sql, values)
        if conflict_columns:
            data = {key: value for key, value in data.items() if key in conflict_columns}

        return self._get_primary_key(table, data)

    def insert_on_conflict_do_update(self, table, data, conflict_columns, set_columns):
        """Write an INSERT statement with an ON CONFLICT clause.

        This is useful to update rows on insert. Intended for
        singl row inserts.

        Args:
            table_name (str): The name of the table to insert into
            data (dict): A dictionary of data to insert into the object
            conflict_columns (list): Columns to check conflict on
            set_columns (list): Columns to update

        Returns:
            (str): The id of the inserted row

        """
        table_name = table()._meta.db_table
        data = self.clean_data(data, table_name)

        set_clause = ",".join([f"{column} = excluded.{column}" for column in set_columns])

        columns_formatted = ", ".join(str(value) for value in data.keys())
        values = list(data.values())
        val_str = ",".join(["%s" for _ in data])
        conflict_columns_formatted = ", ".join(conflict_columns)

        insert_sql = f"""
        INSERT INTO {self.schema}.{table_name}({columns_formatted}) VALUES ({val_str})
         ON CONFLICT ({conflict_columns_formatted}) DO UPDATE SET
         {set_clause}
        """
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(insert_sql, values)

        data = {key: value for key, value in data.items() if key in conflict_columns}

        return self._get_primary_key(table_name, data)

    def _get_primary_key(self, table_name, data):
        """Return the row id for a specific object."""
        with schema_context(self.schema):
            query = self._get_db_obj_query(table_name)
            query = query.filter(**data)
            try:
                row_id = query.first().id
            except AttributeError as err:
                LOG.error("Row in %s does not exist in database.", table_name)
                LOG.error("Failed row data: %s", data)
                raise err
            else:
                return row_id

    def clean_data(self, data, table_name):
        """Clean data for insertion into database.

        Args:
            data (dict): The data to be cleaned
            table_name (str): The table name the data is associated with

        Returns:
            (dict): The data with values converted to required types

        """
        column_types = self.report_schema.column_types[table_name]

        for key, value in data.items():
            if value is None or value == "":
                data[key] = None
                continue
            if column_types.get(key) == int or column_types.get(key) == "BigIntegerField":
                data[key] = self._convert_value(value, int)
            elif column_types.get(key) == float:
                data[key] = self._convert_value(value, float)
            elif column_types.get(key) == Decimal:
                data[key] = self._convert_value(value, Decimal)

        return data

    def _convert_value(self, value, column_type):
        """Convert a single value to the specified column type.

        Args:
            value (var): A value of any type
            column_type (type) A Python type

        Returns:
            (var): The variable converted to type or None if conversion fails.

        """
        if column_type == Decimal:
            try:
                value = Decimal(value).quantize(Decimal(self.decimal_precision))
            except InvalidOperation:
                value = None
        else:
            try:
                value = column_type(value)
            except ValueError as err:
                LOG.warning(err)
                value = None
        return value

    def _execute_raw_sql_query(self, table, sql, start=None, end=None, bind_params=None):
        """Run a SQL statement via a cursor."""
        if start and end:
            LOG.info("Updating %s from %s to %s.", table, start, end)
        else:
            LOG.info("Updating %s", table)

        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            try:
                cursor.execute(sql, params=bind_params)
            except OperationalError as exc:
                db_exc = get_extended_exception_by_type(exc)
                LOG.error(log_json(os.getpid(), str(db_exc), context=db_exc.as_dict()))
                raise db_exc

        LOG.info("Finished updating %s.", table)

    def _execute_presto_raw_sql_query(self, schema, sql, bind_params=None):
        """Execute a single presto query"""
        presto_conn = kpdb.connect(schema=schema)
        presto_cur = presto_conn.cursor()
        presto_cur.execute(sql, bind_params)
        return presto_cur.fetchall()

    def _execute_presto_multipart_sql_query(
        self, schema, sql, bind_params=None, preprocessor=JinjaSql().prepare_query
    ):
        """Execute multiple related SQL queries in Presto."""
        presto_conn = kpdb.connect(schema=self.schema)
        return kpdb.executescript(presto_conn, sql, params=bind_params, preprocessor=preprocessor)

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

    def table_exists_trino(self, table_name):
        """Check if table exists."""
        table_check_sql = f"SHOW TABLES LIKE '{table_name}'"
        table = self._execute_presto_raw_sql_query(self.schema, table_check_sql)
        if table:
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
