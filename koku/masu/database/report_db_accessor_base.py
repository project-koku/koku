#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Database accessor for report data."""
import logging
import uuid
from decimal import Decimal
from decimal import InvalidOperation

import django.apps
from django.db import connection
from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database.koku_database_access import KokuDBAccess
from reporting_common import REPORT_COLUMN_MAP

LOG = logging.getLogger(__name__)


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
            cursor.execute(sql, params=bind_params)
        LOG.info("Finished updating %s.", table)
