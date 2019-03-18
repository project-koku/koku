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
from decimal import Decimal, InvalidOperation

import psycopg2
from sqlalchemy.dialects.postgresql import insert

from masu.config import Config
from masu.database.koku_database_access import KokuDBAccess

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ReportSchema:
    """A container for the reporting table objects."""

    def __init__(self, tables, column_map):
        """Initialize the report schema."""
        self.column_types = {}
        self._set_reporting_tables(tables, column_map)

    def _set_reporting_tables(self, tables, column_map):
        """Load table objects for reference and creation.

        Args:
            report_schema (ReportSchema): A schema struct object with all
                report tables
            column_map (dict): A mapping of report columns to database columns

        """
        column_types = {}
        for table in tables:
            if 'django' in table.__name__:
                continue
            setattr(self, table.__name__, table)
            columns = column_map[table.__name__].values()
            types = {column: getattr(table, column).type.python_type
                     for column in columns}
            column_types.update({table.__name__: types})
            self.column_types = column_types


# pylint: disable=too-many-public-methods
class ReportDBAccessorBase(KokuDBAccess):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns
        """
        super().__init__(schema)
        self.column_map = column_map
        self.report_schema = ReportSchema(self.get_base().classes,
                                          self.column_map)
        self._session = self.get_session()
        self._conn = self._db.connect()
        self._pg2_conn = self._get_psycopg2_connection()
        self._cursor = self._get_psycopg2_cursor()

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager close connections."""
        super().__exit__(exception_type, exception_value, traceback)
        self.close_connections()

    @property
    def decimal_precision(self):
        """Return database precision for decimal values."""
        return f'0E-{Config.REPORTING_DECIMAL_PRECISION}'

    # pylint: disable=no-self-use
    def _get_psycopg2_connection(self):
        """Get a low level database connection."""
        return psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)

    def _get_psycopg2_cursor(self):
        """Get a cursor for the low level database connection."""
        cursor = self._pg2_conn.cursor()
        cursor.execute(f'SET search_path TO {self.schema}')
        return cursor

    def create_temp_table(self, table_name, drop_column=None):
        """Create a temporary table and return the table name."""
        temp_table_name = table_name + '_' + str(uuid.uuid4()).replace('-', '_')
        self._cursor.execute(
            f'CREATE TEMPORARY TABLE {temp_table_name} (LIKE {table_name})'
        )
        if drop_column:
            self._cursor.execute(
                f'ALTER TABLE {temp_table_name} DROP COLUMN {drop_column}'
            )

        return temp_table_name

    def create_new_temp_table(self, table_name, columns):
        """Create a temporary table and return the table name."""
        temp_table_name = table_name + '_' + str(uuid.uuid4()).replace('-', '_')
        base_sql = f'CREATE TEMPORARY TABLE {temp_table_name} '
        column_types = f''
        for column in columns:
            for name, column_type in column.items():
                column_types += (f'{name} {column_type}, ')
        column_types = column_types.strip().rstrip(',')
        column_sql = '({})'.format(column_types)
        table_sql = base_sql + column_sql
        self._cursor.execute(table_sql)

        return temp_table_name

    # pylint: disable=too-many-arguments
    def merge_temp_table(self, table_name, temp_table_name, columns,
                         condition_column, conflict_columns):
        """INSERT temp table rows into the primary table specified.

        Args:
            table_name (str): The main table to insert into
            temp_table_name (str): The temp table to pull from
            columns (list): A list of columns to use in the insert logic

        Returns:
            (None)

        """
        is_finalized_data = False
        column_str = ','.join(columns)
        conflict_col_str = ','.join(conflict_columns)

        set_clause = ','.join([f'{column} = excluded.{column}'
                               for column in columns])
        update_sql = f"""
            INSERT INTO {table_name} ({column_str})
                SELECT {column_str}
                FROM {temp_table_name}
                WHERE {condition_column} IS NOT NULL
                ON CONFLICT ({conflict_col_str}) DO UPDATE
                SET {set_clause}
            """
        self._cursor.execute(update_sql)
        self._pg2_conn.commit()

        row_count = self._cursor.rowcount
        if row_count > 0:
            is_finalized_data = True

        insert_sql = f"""
            INSERT INTO {table_name} ({column_str})
                SELECT {column_str}
                FROM {temp_table_name}
                WHERE {condition_column} IS NULL
                ON CONFLICT DO NOTHING
        """
        self._cursor.execute(insert_sql)
        self._pg2_conn.commit()

        delete_sql = f'DELETE FROM {temp_table_name}'
        self._cursor.execute(delete_sql)
        self._pg2_conn.commit()
        self.vacuum_table(temp_table_name)

        return is_finalized_data

    def vacuum_table(self, table_name):
        """Vacuum a table outside of a transaction."""
        isolation_level = self._pg2_conn.isolation_level
        self._pg2_conn.set_isolation_level(
            psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
        )
        vacuum = f'VACUUM {table_name}'
        self._cursor.execute(vacuum)
        self._pg2_conn.set_isolation_level(isolation_level)

    # pylint: disable=too-many-arguments
    def bulk_insert_rows(self, file_obj, table, columns, sep='\t', null=''):
        r"""Insert many rows using Postgres copy functionality.

        Args:
            file_obj (file): A file-like object containing CSV rows
            table (str): The table name in the databse to copy to
            columns (list): A list of columns in the order of the CSV file
            sep (str): The separator in the file. Default: '\t'
            null (str): How null is represented in the CSV. Default: ''

        """
        self._cursor.copy_from(
            file_obj,
            table,
            sep=sep,
            columns=columns,
            null=null
        )
        self._pg2_conn.commit()

    def close_connections(self, conn=None):
        """Close the low level database connection.

        Args:
            conn (psycopg2.extensions.connection) An optional connection.
                If none is supplied the class's connections are used.

        """
        if conn:
            conn.close()
        else:
            self._cursor.close()
            self._pg2_conn.close()
            self._conn.close()

    # pylint: disable=arguments-differ
    def _get_db_obj_query(self, table_name, columns=None):
        """Return a query on a specific database table.

        Args:
            table_name (str): Which table to query
            columns (list): A list of column names to exclusively return

        Returns:
            (Query): A SQLAlchemy query object

        """
        table = getattr(self.report_schema, table_name)
        if columns:
            entities = [getattr(table, column) for column in columns]
            query = self._session.query(table).with_entities(*entities)
        else:
            query = self._session.query(table)

        return query

    def create_db_object(self, table_name, data):
        """Instantiate a populated database object.

        Args:
            table_name (str): The name of the table to create
            data (dict): A dictionary of data to insert into the object

        Returns:
            (Table): A populated SQLAlchemy table object specified by table_name

        """
        # pylint: disable=invalid-name
        Table = getattr(self.report_schema, table_name)
        data = self.clean_data(data, table_name)

        return Table(**data)

    def insert_on_conflict_do_nothing(self,
                                      table_name,
                                      data,
                                      conflict_columns=None):
        """Write an INSERT statement with an ON CONFLICT clause.

        This is useful to avoid duplicate row inserts. Intended for
        singl row inserts.

        Args:
            table_name (str): The name of the table to insert into
            data (dict): A dictionary of data to insert into the object
            columns (list): A list of columns to check conflict on

        Returns:
            (str): The id of the inserted row

        """
        data = self.clean_data(data, table_name)
        table = getattr(self.report_schema, table_name)
        statement = insert(table).values(**data)

        result = self._conn.execute(
            statement.on_conflict_do_nothing(index_elements=conflict_columns)
        )
        if result.inserted_primary_key:
            return result.inserted_primary_key[0]

        if conflict_columns:
            data = {key: value for key, value in data.items()
                    if key in conflict_columns}

        return self._get_primary_key(table_name, data)

    def insert_on_conflict_do_update(self,
                                     table_name,
                                     data,
                                     conflict_columns,
                                     set_columns):
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
        data = self.clean_data(data, table_name)
        set_data = {key: value for key, value in data.items()
                    if key in set_columns}
        table = getattr(self.report_schema, table_name)
        statement = insert(table).values(**data)

        result = self._conn.execute(
            statement.on_conflict_do_update(
                index_elements=conflict_columns,
                set_=set_data
            )
        )
        if result.inserted_primary_key:
            return result.inserted_primary_key[0]

        data = {key: value for key, value in data.items()
                if key in conflict_columns}

        return self._get_primary_key(table_name, data)

    def _get_primary_key(self, table_name, data):
        """Return the row id for a specific object."""
        query = self._get_db_obj_query(table_name)
        query = query.filter_by(**data)
        try:
            row_id = query.first().id
        except AttributeError as err:
            LOG.error('Row in %s does not exist in database.', table_name)
            LOG.error('Failed row data: %s', data)
            raise err
        else:
            return row_id

    def flush_db_object(self, table):
        """Commit a table row to the database.

        Args:
            table (Table): A SQLAlchemy mapped table object

        """
        self._session.add(table)
        self._session.flush()

    def commit(self):
        """Commit all objects on the current session."""
        self._session.commit()

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
            if value is None or value == '':
                data[key] = None
                continue
            if column_types.get(key) == int:
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
