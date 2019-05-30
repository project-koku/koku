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

"""Test the AWSReportDBAccessor utility object."""
import calendar
import datetime
from decimal import Decimal, InvalidOperation
import types
import random
import string
import uuid
from unittest.mock import patch

import psycopg2
from dateutil import relativedelta
from sqlalchemy.orm.query import Query
from sqlalchemy.sql import func


from masu.database import AWS_CUR_TABLE_MAP
from masu.database.report_db_accessor_base import ReportSchema
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.ocp.common import get_cluster_id_from_provider
from tests import MasuTestCase
from tests.database.helpers import ReportObjectCreator


class ReportSchemaTest(MasuTestCase):
    """Test Cases for the ReportSchema object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = AWSReportDBAccessor(
            schema='acct10001',
            column_map=cls.column_map
        )
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AWS_CUR_TABLE_MAP['bill'],
            AWS_CUR_TABLE_MAP['product'],
            AWS_CUR_TABLE_MAP['pricing'],
            AWS_CUR_TABLE_MAP['reservation']
        ]

    @classmethod
    def tearDownClass(cls):
        """Close the DB session."""
        cls.common_accessor.close_session()
        cls.accessor.close_connections()
        cls.accessor.close_session()

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
        cls.accessor = AWSReportDBAccessor(
            schema='acct10001',
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
        billing_start = datetime.datetime.utcnow().replace(day=1)
        cls.manifest_dict = {
            'assembly_id': '1234',
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_id': 1
        }
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """"Set up a test with database objects."""
        super().setUp()
        if self.accessor._conn.closed:
            self.accessor._conn = self.accessor._db.connect()
        if self.accessor._pg2_conn.closed:
            self.accessor._pg2_conn = self.accessor._get_psycopg2_connection()
        if self.accessor._cursor.closed:
            self.accessor._cursor = self.accessor._get_psycopg2_cursor()
        today = DateAccessor().today_with_timezone('UTC')
        bill = self.creator.create_cost_entry_bill(today)
        cost_entry = self.creator.create_cost_entry(bill, today)
        product = self.creator.create_cost_entry_product()
        pricing = self.creator.create_cost_entry_pricing()
        reservation = self.creator.create_cost_entry_reservation()
        self.creator.create_cost_entry_line_item(
            bill,
            cost_entry,
            product,
            pricing,
            reservation
        )

        self.manifest = self.manifest_accessor.add(**self.manifest_dict)
        self.manifest_accessor.commit()

    def tearDown(self):
        """Return the database to a pre-test state."""
        self.accessor._session.rollback()

        for table_name in self.all_tables:
            tables = self.accessor._get_db_obj_query(table_name).all()
            for table in tables:
                self.accessor._session.delete(table)
        self.accessor.commit()

        manifests = self.manifest_accessor._get_db_obj_query().all()
        for manifest in manifests:
            self.manifest_accessor.delete(manifest)
        self.manifest_accessor.commit()

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

    def test_create_temp_table(self):
        """Test that a temporary table is created."""
        table_name = random.choice(self.all_tables)
        cursor = self.accessor._cursor
        temp_table_name = self.accessor.create_temp_table(table_name)

        exists = """
            SELECT exists(
                SELECT 1
                FROM pg_tables
                WHERE tablename='{table_name}'
            )
        """.format(table_name=temp_table_name)

        cursor.execute(exists)
        result = cursor.fetchone()

        self.assertTrue(result[0])

    def test_merge_temp_table(self):
        """Test that a temp table insert succeeds."""
        table_name = 'test_table'
        columns = ['test_column']
        conflict_columns = columns
        condition_column = columns[0]
        cursor = self.accessor._cursor

        drop_table = f'DROP TABLE IF EXISTS {table_name}'
        cursor.execute(drop_table)

        create_table = f'CREATE TABLE {table_name} (id serial primary key, test_column varchar(8) unique)'
        cursor.execute(create_table)

        count = f'SELECT count(*) FROM {table_name}'
        cursor.execute(count)
        initial_count = cursor.fetchone()[0]

        temp_table_name = self.accessor.create_temp_table(table_name, drop_column='id')

        insert = f'INSERT INTO {temp_table_name} (test_column) VALUES (\'123\')'
        cursor.execute(insert)

        self.accessor.merge_temp_table(table_name, temp_table_name, columns,
                                       condition_column, conflict_columns)

        cursor.execute(count)
        final_count = cursor.fetchone()[0]

        self.assertEqual(initial_count + 1, final_count)


        cursor.execute(drop_table)
        self.accessor._pg2_conn.commit()

    def test_merge_temp_table_with_duplicate(self):
        """Test that a temp table with duplicate row does not insert."""
        table_name = 'test_table'
        columns = ['test_column']
        conflict_columns = columns
        condition_column = columns[0]
        cursor = self.accessor._cursor

        drop_table = f'DROP TABLE IF EXISTS {table_name}'
        cursor.execute(drop_table)

        create_table = f'CREATE TABLE {table_name} (id serial primary key, test_column varchar(8) unique)'
        cursor.execute(create_table)

        insert = f'INSERT INTO {table_name} (test_column) VALUES (\'123\')'
        cursor.execute(insert)

        count = f'SELECT count(*) FROM {table_name}'
        cursor.execute(count)
        initial_count = cursor.fetchone()[0]

        temp_table_name = self.accessor.create_temp_table(table_name, drop_column='id')

        insert = f'INSERT INTO {temp_table_name} (test_column) VALUES (\'123\')'
        cursor.execute(insert)

        self.accessor.merge_temp_table(table_name, temp_table_name, columns,
                                       condition_column, conflict_columns)

        cursor.execute(count)
        final_count = cursor.fetchone()[0]

        self.assertEqual(initial_count, final_count)

        cursor.execute(drop_table)
        self.accessor._pg2_conn.commit()

    def test_merge_temp_table_with_updates(self):
        """Test that rows with invoice ids get updated."""
        table_name = 'test_table'
        columns = ['test_column', 'invoice_id']
        condition_column = columns[1]
        conflict_columns = ['test_column']
        expected_invoice_id = str(uuid.uuid4())
        cursor = self.accessor._cursor

        drop_table = f'DROP TABLE IF EXISTS {table_name}'
        cursor.execute(drop_table)

        create_table = f'CREATE TABLE {table_name} (id serial primary key, test_column varchar(8) unique, invoice_id varchar(64))'
        cursor.execute(create_table)

        insert = f'INSERT INTO {table_name} (test_column) VALUES (\'123\')'
        cursor.execute(insert)

        count = f'SELECT count(*) FROM {table_name}'
        cursor.execute(count)
        initial_count = cursor.fetchone()[0]

        temp_table_name = self.accessor.create_temp_table(table_name, drop_column='id')

        insert = f'INSERT INTO {temp_table_name} (test_column, invoice_id) VALUES (\'123\', \'{expected_invoice_id}\')'
        cursor.execute(insert)

        self.accessor.merge_temp_table(table_name, temp_table_name, columns,
                                       condition_column, conflict_columns)

        invoice_sql = f'SELECT invoice_id FROM {table_name}'
        cursor.execute(invoice_sql)
        invoice_id = cursor.fetchone()
        invoice_id = invoice_id[0] if invoice_id else None

        cursor.execute(count)
        final_count = cursor.fetchone()[0]

        self.assertEqual(initial_count, final_count)
        self.assertEqual(invoice_id, expected_invoice_id)

        cursor.execute(drop_table)
        self.accessor._pg2_conn.commit()

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

    def test_insert_on_conflict_do_update_with_conflict(self):
        """Test that an INSERT succeeds ignoring the conflicting row."""
        table_name = AWS_CUR_TABLE_MAP['reservation']
        data = self.creator.create_columns_for_table(table_name)
        query = self.accessor._get_db_obj_query(table_name)
        initial_res_count = 1
        initial_count = query.count()
        data['number_of_reservations'] = initial_res_count
        row_id = self.accessor.insert_on_conflict_do_update(
            table_name,
            data,
            conflict_columns=['reservation_arn'],
            set_columns=list(data.keys())
        )
        insert_count = query.count()
        row = query.all()[-1]
        self.assertEqual(insert_count, initial_count + 1)
        self.assertEqual(row.number_of_reservations, initial_res_count)

        data['number_of_reservations'] = initial_res_count + 1
        row_id_2 = self.accessor.insert_on_conflict_do_update(
            table_name,
            data,
            conflict_columns=['reservation_arn'],
            set_columns=list(data.keys())
        )
        self.accessor.commit()
        row = query.filter_by(id=row_id_2).first()

        self.assertEqual(insert_count, query.count())
        self.assertEqual(row_id, row_id_2)
        self.assertEqual(row.number_of_reservations, initial_res_count + 1)


    def test_insert_on_conflict_do_update_without_conflict(self):
        """Test that an INSERT succeeds inserting all non-conflicting rows."""
        table_name = AWS_CUR_TABLE_MAP['reservation']
        data = [
            self.creator.create_columns_for_table(table_name),
            self.creator.create_columns_for_table(table_name)
        ]
        query = self.accessor._get_db_obj_query(table_name)

        previous_count = query.count()
        previous_row_id = None
        for entry in data:
            row_id = self.accessor.insert_on_conflict_do_update(
                table_name,
                entry,
                conflict_columns=['reservation_arn'],
                set_columns=list(entry.keys())
            )
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
        self.accessor._session.add(table)
        self.accessor._session.commit()


        p_key = self.accessor._get_primary_key(table_name, data)

        self.assertIsNotNone(p_key)

    def test_get_primary_key_attribute_error(self):
        """Test that an AttributeError is raised on bad primary key lookup."""
        table_name = table_name = AWS_CUR_TABLE_MAP['product']
        data = self.creator.create_columns_for_table(table_name)
        table = self.accessor.create_db_object(table_name, data)
        self.accessor._session.add(table)
        self.accessor._session.commit()

        data['sku'] = ''.join([random.choice(string.digits) for _ in range(5)])
        with self.assertRaises(AttributeError):
            self.accessor._get_primary_key(table_name, data)

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
        column_types = self.report_schema.column_types[table_name]

        data = self.creator.create_columns_for_table(table_name)
        cleaned_data = self.accessor.clean_data(data, table_name)

        for key, value in cleaned_data.items():
            if column_types[key] == datetime.datetime:
                value = self.creator.datetimeify_string(value)
            self.assertIsInstance(value, column_types[key])

    def test_convert_value_decimal_invalid_operation(self):
        """Test that an InvalidOperation is raised and None is returned."""
        dec = Decimal('123342348239472398472309847230984723098427309')

        result = self.accessor._convert_value(dec, Decimal)
        self.assertIsNone(result)

        result = self.accessor._convert_value('', Decimal)
        self.assertIsNone(result)

    def test_convert_value_value_error(self):
        """Test that a value error results in a None value."""
        value = 'Not a Number'
        result = self.accessor._convert_value(value, float)
        self.assertIsNone(result)

    def test_get_cost_entry_bills(self):
        """Test that bills are returned in a dict."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        bill = self.accessor._get_db_obj_query(table_name).first()
        expected_key = (bill.bill_type, bill.payer_account_id, bill.billing_period_start, bill.provider_id)
        # expected = {expected_key: bill.id}

        bill_map = self.accessor.get_cost_entry_bills()

        self.assertIn(expected_key, bill_map)
        self.assertEqual(bill_map[expected_key], bill.id)

    def test_get_cost_entry_bills_by_date(self):
        table_name = AWS_CUR_TABLE_MAP['bill']
        today = datetime.datetime.utcnow()
        bill_start = today.replace(day=1).date()
        bill_id = self.accessor._get_db_obj_query(table_name).first().id
        bills = self.accessor.get_cost_entry_bills_by_date(bill_start)

        self.assertEqual(bill_id, bills[0].id)

    def test_get_bill_query_before_date(self):
        """Test that gets a query for cost entry bills before a date."""
        table_name = AWS_CUR_TABLE_MAP['bill']
        query = self.accessor._get_db_obj_query(table_name)
        first_entry = query.first()

        # Verify that the result is returned for cutoff_date == billing_period_start
        cutoff_date = first_entry.billing_period_start
        cost_entries = self.accessor.get_bill_query_before_date(cutoff_date)
        self.assertEqual(cost_entries.count(), 1)
        self.assertEqual(cost_entries.first().billing_period_start, cutoff_date)

        # Verify that the result is returned for a date later than cutoff_date
        later_date = cutoff_date + relativedelta.relativedelta(months=+1)
        later_cutoff = later_date.replace(month=later_date.month, day=15)
        cost_entries = self.accessor.get_bill_query_before_date(later_cutoff)
        self.assertEqual(cost_entries.count(), 1)
        self.assertEqual(cost_entries.first().billing_period_start, cutoff_date)

        # Verify that no results are returned for a date earlier than cutoff_date
        earlier_date = cutoff_date + relativedelta.relativedelta(months=-1)
        earlier_cutoff = earlier_date.replace(month=earlier_date.month, day=15)
        cost_entries = self.accessor.get_bill_query_before_date(earlier_cutoff)
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
        expected_key = (first_entry.sku,
                        first_entry.product_name,
                        first_entry.region)
        self.assertIn(expected_key, products)

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
        table_name = AWS_CUR_TABLE_MAP['reservation']
        query = self.accessor._get_db_obj_query(table_name)
        count = query.count()
        first_entry = query.first()

        reservations = self.accessor.get_reservations()

        self.assertIsInstance(reservations, dict)
        self.assertEqual(len(reservations.keys()), count)
        self.assertIn(first_entry.reservation_arn, reservations)

    def test_populate_line_item_daily_table(self):
        """Test that the daily table is populated."""
        ce_table_name = AWS_CUR_TABLE_MAP['cost_entry']
        daily_table_name = AWS_CUR_TABLE_MAP['line_item_daily']

        ce_table = getattr(self.accessor.report_schema, ce_table_name)
        daily_table = getattr(self.accessor.report_schema, daily_table_name)

        for _ in range(10):
            bill = self.creator.create_cost_entry_bill()
            cost_entry = self.creator.create_cost_entry(bill)
            product = self.creator.create_cost_entry_product()
            pricing = self.creator.create_cost_entry_pricing()
            reservation = self.creator.create_cost_entry_reservation()
            self.creator.create_cost_entry_line_item(
                bill,
                cost_entry,
                product,
                pricing,
                reservation
            )

        bills = self.accessor.get_cost_entry_bills_query_by_provider(1)
        bill_ids = [str(bill.id) for bill in bills.all()]

        start_date, end_date = self.accessor._session.query(
            func.min(ce_table.interval_start),
            func.max(ce_table.interval_start)
        ).first()

        start_date = start_date.replace(hour=0, minute=0, second=0,
                                        microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0,
                                        microsecond=0)

        query = self.accessor._get_db_obj_query(daily_table_name)
        initial_count = query.count()

        self.accessor.populate_line_item_daily_table(start_date, end_date, bill_ids)


        self.assertNotEqual(query.count(), initial_count)

        result_start_date, result_end_date = self.accessor._session.query(
            func.min(daily_table.usage_start),
            func.max(daily_table.usage_start)
        ).first()

        self.assertEqual(result_start_date, start_date)
        self.assertEqual(result_end_date, end_date)

        entry = query.first()

        summary_columns = [
            'cost_entry_product_id', 'cost_entry_pricing_id',
            'cost_entry_reservation_id', 'line_item_type', 'usage_account_id',
            'usage_start', 'usage_end', 'product_code', 'usage_type',
            'operation', 'availability_zone', 'resource_id', 'usage_amount',
            'normalization_factor', 'normalized_usage_amount', 'currency_code',
            'unblended_rate', 'unblended_cost', 'blended_rate', 'blended_cost',
            'public_on_demand_cost', 'public_on_demand_rate', 'tags'
        ]

        for column in summary_columns:
            self.assertIsNotNone(getattr(entry, column))

        self.assertNotEqual(getattr(entry, 'tags'), {})

    def test_populate_line_item_daily_summary_table(self):
        """Test that the daily summary table is populated."""
        ce_table_name = AWS_CUR_TABLE_MAP['cost_entry']
        summary_table_name = AWS_CUR_TABLE_MAP['line_item_daily_summary']

        ce_table = getattr(self.accessor.report_schema, ce_table_name)
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        for _ in range(10):
            bill = self.creator.create_cost_entry_bill()
            cost_entry = self.creator.create_cost_entry(bill)
            product = self.creator.create_cost_entry_product()
            pricing = self.creator.create_cost_entry_pricing()
            reservation = self.creator.create_cost_entry_reservation()
            self.creator.create_cost_entry_line_item(
                bill,
                cost_entry,
                product,
                pricing,
                reservation
            )

        bills = self.accessor.get_cost_entry_bills_query_by_provider(1)
        bill_ids = [str(bill.id) for bill in bills.all()]

        table_name = AWS_CUR_TABLE_MAP['line_item']
        tag_query = self.accessor._get_db_obj_query(table_name)
        possible_keys = []
        possible_values = []
        for item in tag_query:
            possible_keys += list(item.tags.keys())
            possible_values += list(item.tags.values())

        start_date, end_date = self.accessor._session.query(
            func.min(ce_table.interval_start),
            func.max(ce_table.interval_start)
        ).first()

        start_date = start_date.replace(hour=0, minute=0, second=0,
                                        microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0,
                                        microsecond=0)

        query = self.accessor._get_db_obj_query(summary_table_name)
        initial_count = query.count()
        self.accessor.populate_line_item_daily_table(start_date, end_date, bill_ids)
        self.accessor.populate_line_item_daily_summary_table(start_date,
                                                              end_date,
                                                              bill_ids)

        self.assertNotEqual(query.count(), initial_count)

        result_start_date, result_end_date = self.accessor._session.query(
            func.min(summary_table.usage_start),
            func.max(summary_table.usage_start)
        ).first()

        self.assertEqual(result_start_date, start_date)
        self.assertEqual(result_end_date, end_date)

        entry = query.first()

        summary_columns = [
            'usage_start', 'usage_end', 'usage_account_id',
            'product_code', 'product_family', 'availability_zone', 'region',
            'instance_type', 'unit', 'resource_count', 'usage_amount',
            'normalization_factor', 'normalized_usage_amount', 'currency_code',
            'unblended_rate', 'unblended_cost', 'blended_rate', 'blended_cost',
            'public_on_demand_cost', 'public_on_demand_rate', 'tags'
        ]

        for column in summary_columns:
            self.assertIsNotNone(getattr(entry, column))

        found_keys = []
        found_values = []
        for item in query.all():
            found_keys += list(item.tags.keys())
            found_values += list(item.tags.values())

        self.assertEqual(set(sorted(possible_keys)), set(sorted(found_keys)))
        self.assertEqual(set(sorted(possible_values)), set(sorted(found_values)))

    def test_populate_awstags_summary_table(self):
        """Test that the AWS tags summary table is populated."""
        bill_ids = []
        ce_table_name = AWS_CUR_TABLE_MAP['cost_entry']
        tags_summary_name = AWS_CUR_TABLE_MAP['tags_summary']

        ce_table = getattr(self.accessor.report_schema, ce_table_name)

        today = DateAccessor().today_with_timezone('UTC')
        last_month = today - relativedelta.relativedelta(months=1)

        for cost_entry_date in (today, last_month):
            bill = self.creator.create_cost_entry_bill(cost_entry_date)
            bill_ids.append(str(bill.id))
            cost_entry = self.creator.create_cost_entry(bill, cost_entry_date)
            for family in ['Storage', 'Compute Instance', 'Database Storage',
                           'Database Instance']:
                product = self.creator.create_cost_entry_product(family)
                pricing = self.creator.create_cost_entry_pricing()
                reservation = self.creator.create_cost_entry_reservation()
                self.creator.create_cost_entry_line_item(
                    bill,
                    cost_entry,
                    product,
                    pricing,
                    reservation
                )

        start_date, end_date = self.accessor._session.query(
            func.min(ce_table.interval_start),
            func.max(ce_table.interval_start)
        ).first()

        query = self.accessor._get_db_obj_query(tags_summary_name)
        initial_count = query.count()

        self.accessor.populate_line_item_daily_table(start_date, end_date, bill_ids)
        self.accessor.populate_line_item_daily_summary_table(start_date,
                                                              end_date,
                                                              bill_ids)
        self.accessor.populate_tags_summary_table()

        self.assertNotEqual(query.count(), initial_count)
        tags = query.all()
        tag_keys = [tag.key for tag in tags]

        self.accessor._cursor.execute(
            """SELECT DISTINCT jsonb_object_keys(tags)
                FROM reporting_awscostentrylineitem_daily"""
        )

        expected_tag_keys = self.accessor._cursor.fetchall()
        expected_tag_keys = [tag[0] for tag in expected_tag_keys]

        self.assertEqual(sorted(tag_keys), sorted(expected_tag_keys))

    def test_populate_ocp_on_aws_cost_daily_summary(self):
        """Test that the OCP on AWS cost summary table is populated."""
        summary_table_name = AWS_CUR_TABLE_MAP['ocp_on_aws_daily_summary']
        project_summary_table_name = AWS_CUR_TABLE_MAP['ocp_on_aws_project_daily_summary']
        bill_ids = []

        summary_table = getattr(self.accessor.report_schema, summary_table_name)
        project_table = getattr(self.accessor.report_schema, project_summary_table_name)

        today = DateAccessor().today_with_timezone('UTC')
        last_month = today - relativedelta.relativedelta(months=1)
        resource_id = 'i-12345'
        for cost_entry_date in (today, last_month):
            bill = self.creator.create_cost_entry_bill(cost_entry_date)
            bill_ids.append(str(bill.id))
            cost_entry = self.creator.create_cost_entry(bill, cost_entry_date)
            product = self.creator.create_cost_entry_product('Compute Instance')
            pricing = self.creator.create_cost_entry_pricing()
            reservation = self.creator.create_cost_entry_reservation()
            self.creator.create_cost_entry_line_item(
                bill,
                cost_entry,
                product,
                pricing,
                reservation,
                resource_id=resource_id
            )

        self.accessor.populate_line_item_daily_table(last_month, today, bill_ids)

        li_table_name = AWS_CUR_TABLE_MAP['line_item']
        li_table = getattr(self.accessor.report_schema, li_table_name)

        sum_aws_cost = self.accessor._session.query(
            func.sum(li_table.unblended_cost)
        ).first()

        with OCPReportDBAccessor(self.test_schema, self.column_map) as ocp_accessor:
            cluster_id = self.ocp_provider_resource_name
            with ProviderDBAccessor(provider_uuid=self.ocp_test_provider_uuid) as provider_access:
                provider_id = provider_access.get_provider().id

            for cost_entry_date in (today, last_month):
                period = self.creator.create_ocp_report_period(cost_entry_date, provider_id=provider_id, cluster_id=cluster_id)
                report = self.creator.create_ocp_report(period, cost_entry_date)
                self.creator.create_ocp_usage_line_item(
                    period,
                    report,
                    resource_id=resource_id
                )
            cluster_id = get_cluster_id_from_provider(self.ocp_test_provider_uuid)
            ocp_accessor.populate_line_item_daily_table(last_month, today, cluster_id)

        query = self.accessor._get_db_obj_query(summary_table_name)
        initial_count = query.count()

        self.accessor.populate_ocp_on_aws_cost_daily_summary(last_month,
                                                             today)

        self.assertNotEqual(query.count(), initial_count)

        sum_cost = self.accessor._session.query(
            func.sum(summary_table.unblended_cost)
        ).first()

        sum_project_cost = self.accessor._session.query(
            func.sum(project_table.unblended_cost)
        ).first()

        self.assertEqual(sum_cost, sum_project_cost)
        self.assertLessEqual(sum_cost, sum_aws_cost)
