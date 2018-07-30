#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Test the ReportDBAccessor utility object."""
import datetime
from decimal import Decimal
import types
import random

import psycopg2
from sqlalchemy.orm.query import Query

from masu.database import AWS_CUR_TABLE_MAP
from masu.database.report_db_accessor import ReportDBAccessor, ReportSchema
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from tests import MasuTestCase
from tests.database.helpers import ReportObjectCreator


class ReportSchemaTest(MasuTestCase):
    """Test Cases for the ReportSchema object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = ReportDBAccessor(
            schema='testcustomer',
            column_map=cls.column_map
        )
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AWS_CUR_TABLE_MAP['bill'],
            AWS_CUR_TABLE_MAP['product'],
            AWS_CUR_TABLE_MAP['pricing'],
            AWS_CUR_TABLE_MAP['reservation']
        ]

    def test_init(self):
        """Test the initializer."""
        tables = self.accessor.get_base().classes
        report_schema = ReportSchema(tables, self.column_map)

        for table_name in self.all_tables:
            self.assertIsNotNone(getattr(report_schema, table_name))

        self.assertNotEqual(report_schema.column_types, {})

    def test_get_reporting_tables(self):
        """Test that the report schema is populated with a column map."""
        tables = self.accessor.get_base().classes
        report_schema = ReportSchema(tables, self.column_map)

        report_schema._set_reporting_tables(
            tables,
            self.accessor.column_map
        )

        for table in self.all_tables:
            self.assertIsNotNone(getattr(report_schema, table))

        self.assertTrue(hasattr(report_schema, 'column_types'))

        column_types = report_schema.column_types

        for table in self.all_tables:
            self.assertIn(table, column_types)

        table_types = column_types[random.choice(self.all_tables)]

        python_types = list(types.__builtins__.values())
        python_types.extend([datetime.datetime, Decimal])

        for table_type in table_types.values():
            self.assertIn(table_type, python_types)


class ReportDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = ReportDBAccessor(
            schema='testcustomer',
            column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(
            cls.accessor,
            cls.column_map,
            cls.report_schema.column_types
        )
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AWS_CUR_TABLE_MAP['bill'],
            AWS_CUR_TABLE_MAP['product'],
            AWS_CUR_TABLE_MAP['pricing'],
            AWS_CUR_TABLE_MAP['reservation']
        ]

    def setUp(self):
        """"Set up a test with database objects."""
        bill_id = self.creator.create_cost_entry_bill()
        cost_entry_id = self.creator.create_cost_entry(bill_id)
        product_id = self.creator.create_cost_entry_product()
        pricing_id = self.creator.create_cost_entry_pricing()
        reservation_id = self.creator.create_cost_entry_reservation()
        self.creator.create_cost_entry_line_item(
            bill_id,
            cost_entry_id,
            product_id,
            pricing_id,
            reservation_id
        )

    def tearDown(self):
        """Return the database to a pre-test state."""
        self.accessor._session.rollback()

        for table_name in self.all_tables:
            tables = self.accessor._get_db_obj_query(table_name).all()
            for table in tables:
                self.accessor._session.delete(table)
        self.accessor.commit()

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)
        self.assertIsNotNone(self.accessor._session)
        self.assertIsNotNone(self.accessor._conn)
        self.assertIsNotNone(self.accessor._cursor)

    def test_get_psycopg2_connection(self):
        """Test the psycopg2 connection."""
        conn = self.accessor._get_psycopg2_connection()

        self.assertIsInstance(conn, psycopg2.extensions.connection)

    def test_get_psycopg2_cursor(self):
        """Test that a psycopg2 cursor is returned."""
        cursor = self.accessor._get_psycopg2_cursor()

        self.assertIsInstance(cursor, psycopg2.extensions.cursor)


    def test_close_connections_with_arg(self):
        """Test that the passed in psycopg2 connection is closed."""
        conn = self.accessor._get_psycopg2_connection()

        self.accessor.close_connections(conn)

        self.assertTrue(conn.closed)

    def test_close_connections_default(self):
        """Test that the accessor's psycopg2 connection is closed."""
        self.accessor.close_connections()

        self.assertTrue(self.accessor._conn.closed)
        self.assertTrue(self.accessor._pg2_conn.closed)
        # Return the accessor's connection to its open state
        self.accessor._conn = self.accessor._db.connect()
        self.accessor._pg2_conn = self.accessor._get_psycopg2_connection()

    def test_get_db_obj_query_default(self):
        """Test that a query is returned."""
        table_name = random.choice(self.all_tables)

        query = self.accessor._get_db_obj_query(table_name)

        self.assertIsInstance(query, Query)

    def test_get_db_obj_query_with_columns(self):
        """Test that a query is returned with limited columns."""
        table_name = random.choice(self.foreign_key_tables)
        columns = list(self.column_map[table_name].values())

        selected_columns = [random.choice(columns) for _ in range(2)]
        missing_columns = set(columns).difference(selected_columns)

        query = self.accessor._get_db_obj_query(
            table_name,
            columns=selected_columns
        )

        self.assertIsInstance(query, Query)

        result = query.first()

        for column in selected_columns:
            self.assertTrue(hasattr(result, column))

        for column in missing_columns:
            self.assertFalse(hasattr(result, column))

    def test_bulk_insert_rows(self):
        """Test that the bulk insert method inserts line items."""
        # Get data commited for foreign key relationships to work
        self.accessor.commit()

        table_name = AWS_CUR_TABLE_MAP['line_item']
        table = getattr(self.report_schema, table_name)
        column_map = self.column_map[table_name]
        query = self.accessor._get_db_obj_query(table_name)
        initial_count = query.count()
        cost_entry = query.first()

        data_dict = self.creator.create_columns_for_table(table_name)
        data_dict['cost_entry_bill_id'] = cost_entry.cost_entry_bill_id
        data_dict['cost_entry_id'] = cost_entry.cost_entry_id
        data_dict['cost_entry_product_id'] = cost_entry.cost_entry_product_id
        data_dict['cost_entry_pricing_id'] = cost_entry.cost_entry_pricing_id
        data_dict['cost_entry_reservation_id'] = cost_entry.cost_entry_reservation_id

        columns = list(data_dict.keys())
        values = list(data_dict.values())
        file_obj = self.creator.create_csv_file_stream(values)

        self.accessor.bulk_insert_rows(file_obj, table_name, columns)

        final_count = query.count()
        new_line_item = query.order_by(table.id.desc()).first()

        self.assertTrue(final_count > initial_count)

        for column in columns:
            value = getattr(new_line_item, column)
            if isinstance(value, datetime.datetime):
                value = self.creator.stringify_datetime(value)
            self.assertEqual(value, data_dict[column])

    def test_create_db_object(self):
        """Test that a mapped database object is returned."""
        table = random.choice(self.all_tables)
        data = self.creator.create_columns_for_table(table)

        row = self.accessor.create_db_object(table, data)

        for column, value in data.items():
            self.assertEqual(getattr(row, column), value)

    def test_insert_on_conflict_do_nothing_with_conflict(self):
        """Test that an INSERT succeeds ignoring the conflicting row."""
        table_name = AWS_CUR_TABLE_MAP['product']
        data = self.creator.create_columns_for_table(table_name)
        query = self.accessor._get_db_obj_query(table_name)

        initial_count = query.count()

        row_id = self.accessor.insert_on_conflict_do_nothing(table_name, data)

        insert_count = query.count()

        self.assertEqual(insert_count, initial_count + 1)

        row_id_2 = self.accessor.insert_on_conflict_do_nothing(
            table_name,
            data
        )

        self.assertEqual(insert_count, query.count())
        self.assertEqual(row_id, row_id_2)


    def test_insert_on_conflict_do_nothing_without_conflict(self):
        """Test that an INSERT succeeds inserting all non-conflicting rows."""
        table_name = random.choice(self.foreign_key_tables)
        data = [
            self.creator.create_columns_for_table(table_name),
            self.creator.create_columns_for_table(table_name)
        ]
        query = self.accessor._get_db_obj_query(table_name)

        previous_count = query.count()
        previous_row_id = None
        for entry in data:
            row_id = self.accessor.insert_on_conflict_do_nothing(table_name, entry)
            count = query.count()

            self.assertEqual(count, previous_count + 1)
            self.assertNotEqual(row_id, previous_row_id)

            previous_count = count
            previous_row_id = row_id

    def test_get_primary_key(self):
        """Test that a primary key is returned."""
        table_name = random.choice(self.foreign_key_tables)
        data = self.creator.create_columns_for_table(table_name)
        table = self.accessor.create_db_object(table_name, data)
        self.accessor.session.add(table)
        self.accessor.session.commit()


        p_key = self.accessor._get_primary_key(table_name, data)

        self.assertIsNotNone(p_key)

    def test_flush_db_object(self):
        """Test that the database flush moves the object to the database."""
        self.accessor._session.commit()
        table = random.choice(self.foreign_key_tables)
        data = self.creator.create_columns_for_table(table)
        initial_row_count = self.accessor._get_db_obj_query(table).count()
        row = self.accessor.create_db_object(table, data)

        self.accessor.flush_db_object(row)
        self.assertIsNotNone(row.id)

        row_count = self.accessor._get_db_obj_query(table).count()
        self.assertTrue(row_count > initial_row_count)
        self.accessor._session.rollback()
        final_row_count = self.accessor._get_db_obj_query(table).count()
        self.assertEqual(initial_row_count, final_row_count)

    def test_clean_data(self):
        """Test that data cleaning produces proper data types."""
        table_name = random.choice(self.all_tables)
        table = getattr(self.report_schema, table_name)
        column_types = self.report_schema.column_types[table_name]

        data = self.creator.create_columns_for_table(table_name)
        cleaned_data = self.accessor.clean_data(data, table_name)

        for key, value in cleaned_data.items():
            if column_types[key] == datetime.datetime:
                value = self.creator.datetimeify_string(value)
            self.assertIsInstance(value, column_types[key])

    def test_get_current_cost_entry_bill(self):
        """Test that the most recent cost entry bill is returned."""
        table_name = 'reporting_awscostentrybill'
        bill_id = self.accessor._get_db_obj_query(table_name).first().id
        bill = self.accessor.get_current_cost_entry_bill()

        self.assertEqual(bill_id, bill.id)

    def test_get_bill_query_before_date(self):
        """Test that gets a query for cost entry bills before a date."""
        table_name = 'reporting_awscostentrybill'
        query = self.accessor._get_db_obj_query(table_name)
        first_entry = query.first()

        # Verify that the result is returned for cutoff_date == billing_period_start
        cutoff_date = first_entry.billing_period_start
        cost_entries = self.accessor.get_bill_query_before_date(cutoff_date)
        self.assertEqual(cost_entries.count(), 1)
        self.assertEqual(cost_entries.first().billing_period_start, cutoff_date)

        # Verify that the result is returned for a date earlier than cutoff_date
        earlier_cutoff = cutoff_date.replace(month=cutoff_date.month-1)
        cost_entries = self.accessor.get_bill_query_before_date(earlier_cutoff)
        self.assertEqual(cost_entries.count(), 1)
        self.assertEqual(cost_entries.first().billing_period_start, cutoff_date)

        # Verify that the result is returned for a date later than cutoff_date
        later_cutoff = cutoff_date.replace(month=cutoff_date.month+1)
        cost_entries = self.accessor.get_bill_query_before_date(later_cutoff)
        self.assertEqual(cost_entries.count(), 0)

    def test_get_lineitem_query_for_billid(self):
        """Test that gets a cost entry line item query given a bill id."""
        table_name = 'reporting_awscostentrybill'

        # Verify that the line items for the test bill_id are returned
        bill_id = self.accessor._get_db_obj_query(table_name).first().id
        line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
        self.assertEqual(line_item_query.count(), 1)
        self.assertEqual(line_item_query.first().cost_entry_bill_id, bill_id)

        # Verify that no line items are returned for a missing bill_id
        wrong_bill_id = bill_id + 1
        line_item_query = self.accessor.get_lineitem_query_for_billid(wrong_bill_id)
        self.assertEqual(line_item_query.count(), 0)

    def test_get_cost_entry_query_for_billid(self):
        """Test that gets a cost entry query given a bill id."""
        table_name = 'reporting_awscostentrybill'

        # Verify that the line items for the test bill_id are returned
        bill_id = self.accessor._get_db_obj_query(table_name).first().id

        cost_entry_query = self.accessor.get_cost_entry_query_for_billid(bill_id)
        self.assertEqual(cost_entry_query.count(), 1)
        self.assertEqual(cost_entry_query.first().bill_id, bill_id)

        # Verify that no line items are returned for a missing bill_id
        wrong_bill_id = bill_id + 1
        cost_entry_query = self.accessor.get_cost_entry_query_for_billid(wrong_bill_id)
        self.assertEqual(cost_entry_query.count(), 0)

    def test_get_cost_entries(self):
        """Test that a dict of cost entries are returned."""
        table_name = 'reporting_awscostentry'
        query = self.accessor._get_db_obj_query(table_name)
        count = query.count()
        first_entry = query.first()
        cost_entries = self.accessor.get_cost_entries()

        self.assertIsInstance(cost_entries, dict)
        self.assertEqual(len(cost_entries.keys()), count)
        self.assertIn(first_entry.id, cost_entries.values())

    def test_get_products(self):
        """Test that a dict of products are returned."""
        table_name = 'reporting_awscostentryproduct'
        query = self.accessor._get_db_obj_query(table_name)
        count = query.count()
        first_entry = query.first()
        products = self.accessor.get_products()

        self.assertIsInstance(products, dict)
        self.assertEqual(len(products.keys()), count)
        self.assertIn(first_entry.sku, products)

    def test_get_pricing(self):
        """Test that a dict of pricing is returned."""
        table_name = 'reporting_awscostentrypricing'
        query = self.accessor._get_db_obj_query(table_name)
        count = query.count()
        first_entry = query.first()

        pricing = self.accessor.get_pricing()

        self.assertIsInstance(pricing, dict)
        self.assertEqual(len(pricing.keys()), count)
        self.assertIn(first_entry.id, pricing.values())

    def test_get_reservations(self):
        """Test that a dict of reservations are returned."""
        table_name = 'reporting_awscostentryreservation'
        query = self.accessor._get_db_obj_query(table_name)
        count = query.count()
        first_entry = query.first()

        reservations = self.accessor.get_reservations()

        self.assertIsInstance(reservations, dict)
        self.assertEqual(len(reservations.keys()), count)
        self.assertIn(first_entry.reservation_arn, reservations)
