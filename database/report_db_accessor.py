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
from decimal import Decimal

import psycopg2
from sqlalchemy.dialects.postgresql import insert

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.koku_database_access import KokuDBAccess

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ReportSchema:
    """A container for the reporting table objects."""

    def __init__(self, tables, column_map):
        """Initialize the report schema."""
        self.column_types = {}
        self.reporting_awscostentry = None
        self.reporting_awscostentrybill = None
        self.reporting_awscostentrylineitem = None
        self.reporting_awscostentryproduct = None
        self.reporting_awscostentrypricing = None
        # pylint: disable=invalid-name
        self.reporting_awscostentryreservation = None
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


class ReportDBAccessor(KokuDBAccess):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns
        """
        super().__init__(schema)
        self._datetime_format = Config.AWS_DATETIME_STR_FORMAT
        self.column_map = column_map
        self.report_schema = ReportSchema(self.get_base().classes,
                                          self.column_map)
        self.session = self.get_session()
        self._conn = self._db.connect()
        self._pg2_conn = self._get_psycopg2_connection()
        self._cursor = self._get_psycopg2_cursor()

    # pylint: disable=no-self-use
    def _get_psycopg2_connection(self):
        """Get a low level database connection."""
        return psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)

    def _get_psycopg2_cursor(self):
        """Get a cursor for the low level database connection."""
        cursor = self._pg2_conn.cursor()
        cursor.execute(f'SET search_path TO {self.schema}')
        return cursor

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
            query = self.session.query(table).with_entities(*entities)
        else:
            query = self.session.query(table)

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
                                      columns=None):
        """Write an INSERT statement with an ON CONFLICT clause.

        This is useful to avoid duplicate row inserts. Intended for
        singl row inserts.

        Args:
            table_name (str): The name of the table to create
            data (dict): A dictionary of data to insert into the object
            columns (list): A list of columns to check conflict on

        Returns:
            (str): The insert statement to be executed

        """
        data = self.clean_data(data, table_name)
        table = getattr(self.report_schema, table_name)
        statement = insert(table).values(**data)

        result = self._conn.execute(
            statement.on_conflict_do_nothing(index_elements=columns)
        )
        if result.inserted_primary_key:
            return result.inserted_primary_key[0]

        return self._get_primary_key(table_name, data)

    def _get_primary_key(self, table_name, data):
        """Return the row id for a specific object."""
        query = self._get_db_obj_query(table_name)
        query = query.filter_by(**data)
        return query.first().id

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
            if not value:
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
        try:
            value = column_type(value)
        except ValueError as err:
            LOG.warning(err)
            value = None
        return value

    def get_current_cost_entry_bill(self, bill_id=None):
        """Get the most recent cost entry bill object."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        billing_start = getattr(
            getattr(self.report_schema, table_name),
            'billing_period_start'
        )
        if bill_id is not None:
            return self._get_db_obj_query(table_name).filter(id=bill_id).first()

        return self._get_db_obj_query(table_name)\
            .order_by(billing_start.desc())\
            .first()

    def get_bill_query_before_date(self, date):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        billing_start = getattr(
            getattr(self.report_schema, table_name),
            'billing_period_start'
        )
        base_query = self._get_db_obj_query(table_name)
        cost_entry_bill_query = base_query.filter(date <= billing_start)
        return cost_entry_bill_query

    def get_lineitem_query_for_billid(self, bill_id):
        """Get the AWS cost entry line item for a given bill query."""
        table_name = AWS_CUR_TABLE_MAP['line_item']
        cost_entry_bill_id = getattr(
            getattr(self.report_schema, table_name),
            'cost_entry_bill_id'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(cost_entry_bill_id == bill_id)
        return line_item_query

    def get_cost_entry_query_for_billid(self, bill_id):
        """Get the AWS cost entry data for a given bill query."""
        table_name = AWS_CUR_TABLE_MAP['cost_entry']

        cost_entry_bill_id = getattr(
            getattr(self.report_schema, table_name),
            'bill_id'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(cost_entry_bill_id == bill_id)
        return line_item_query

    def get_cost_entries(self):
        """Make a mapping of cost entries by start time."""
        table_name = AWS_CUR_TABLE_MAP['cost_entry']
        interval_start = getattr(
            getattr(self.report_schema, table_name),
            'interval_start'
        )
        cost_entries = self._get_db_obj_query(table_name)\
            .order_by(interval_start.desc())\
            .all()

        return {entry.interval_start.strftime(self._datetime_format): entry.id
                for entry in cost_entries}

    def get_products(self):
        """Make a mapping of product sku to product objects."""
        table_name = AWS_CUR_TABLE_MAP['product']
        columns = ['id', 'sku']
        products = self._get_db_obj_query(table_name, columns=columns).all()

        return {product.sku: product.id for product in products}

    def get_pricing(self):
        """Make a mapping of pricing values string to pricing objects."""
        table_name = AWS_CUR_TABLE_MAP['pricing']
        pricing = self._get_db_obj_query(table_name).all()

        return {f'{p.public_on_demand_cost}-{p.public_on_demand_rate}-{p.term}-{p.unit}': p.id
                for p in pricing}

    def get_reservations(self):
        """Make a mapping of reservation ARN to reservation objects."""
        table_name = AWS_CUR_TABLE_MAP['reservation']
        columns = ['id', 'reservation_arn']
        reservs = self._get_db_obj_query(table_name, columns=columns).all()

        return {reservation.reservation_arn: reservation.id
                for reservation in reservs}
