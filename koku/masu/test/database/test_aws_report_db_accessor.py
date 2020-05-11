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
import datetime
import decimal
import random
import string
from decimal import Decimal

import django.apps
from dateutil import relativedelta
from django.db import connection
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from django.db.models.query import QuerySet
from tenant_schemas.utils import schema_context

from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_db_accessor_base import ReportSchema
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import map_django_field_type_to_python_type
from masu.test.database.helpers import ReportObjectCreator
from reporting.provider.aws.models import AWSCostEntryProduct
from reporting.provider.aws.models import AWSCostEntryReservation
from reporting_common import REPORT_COLUMN_MAP


class ReportSchemaTest(MasuTestCase):
    """Test Cases for the ReportSchema object."""

    def setUp(self):
        """Set up the test class with required objects."""
        super().setUp()
        self.accessor = AWSReportDBAccessor(schema=self.schema)
        self.all_tables = list(AWS_CUR_TABLE_MAP.values())
        self.foreign_key_tables = [
            AWS_CUR_TABLE_MAP["bill"],
            AWS_CUR_TABLE_MAP["product"],
            AWS_CUR_TABLE_MAP["pricing"],
            AWS_CUR_TABLE_MAP["reservation"],
        ]

    def test_init(self):
        """Test the initializer."""
        tables = django.apps.apps.get_models()
        report_schema = ReportSchema(tables)

        for table_name in self.all_tables:
            self.assertIsNotNone(getattr(report_schema, table_name))

        self.assertNotEqual(report_schema.column_types, {})

    def test_get_reporting_tables(self):
        """Test that the report schema is populated with a column map."""
        tables = django.apps.apps.get_models()
        report_schema = ReportSchema(tables)

        report_schema._set_reporting_tables(tables)

        for table in self.all_tables:
            self.assertIsNotNone(getattr(report_schema, table))

        self.assertTrue(hasattr(report_schema, "column_types"))

        column_types = report_schema.column_types

        for table in self.all_tables:
            self.assertIn(table, column_types)

        table_types = column_types[random.choice(self.all_tables)]

        django_field_types = [
            "IntegerField",
            "FloatField",
            "JSONField",
            "DateTimeField",
            "DecimalField",
            "CharField",
            "TextField",
            "PositiveIntegerField",
        ]
        for table_type in table_types.values():
            self.assertIn(table_type, django_field_types)


class AWSReportDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = AWSReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema)

        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AWS_CUR_TABLE_MAP["bill"],
            AWS_CUR_TABLE_MAP["product"],
            AWS_CUR_TABLE_MAP["pricing"],
            AWS_CUR_TABLE_MAP["reservation"],
        ]
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        today = DateAccessor().today_with_timezone("UTC")
        billing_start = today.replace(day=1)

        self.cluster_id = "testcluster"

        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_id": self.aws_provider.uuid,
        }
        self.creator.create_cost_entry_reservation()

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_create_temp_table(self):
        """Test that a temporary table is created."""
        table_name = "test_table"
        with connection.cursor() as cursor:
            drop_table = f"DROP TABLE IF EXISTS {table_name}"
            cursor.execute(drop_table)

            create_table = f"CREATE TABLE {table_name} (id serial primary key, test_column varchar(8) unique)"
            cursor.execute(create_table)

            temp_table_name = self.accessor.create_temp_table(table_name)

            exists = """
                SELECT exists(
                    SELECT 1
                    FROM pg_tables
                    WHERE tablename='{table_name}'
                )
            """.format(
                table_name=temp_table_name
            )

            cursor.execute(exists)
            result = cursor.fetchone()

            self.assertTrue(result[0])

    def test_get_db_obj_query_default(self):
        """Test that a query is returned."""
        table_name = random.choice(self.all_tables)
        query = self.accessor._get_db_obj_query(table_name)
        self.assertIsInstance(query, QuerySet)

    def test_get_db_obj_query_with_columns(self):
        """Test that a query is returned with limited columns."""
        table_name = random.choice(self.foreign_key_tables)
        columns = list(REPORT_COLUMN_MAP[table_name].values())

        selected_columns = [random.choice(columns) for _ in range(2)]
        missing_columns = set(columns).difference(selected_columns)

        query = self.accessor._get_db_obj_query(table_name, columns=selected_columns)
        with schema_context(self.schema):
            self.assertIsInstance(query, QuerySet)
            result = query.first()
            for column in selected_columns:
                self.assertTrue(column in result)

            for column in missing_columns:
                self.assertFalse(column in result)

    def _create_columns_from_data(self, datadict):
        columns = {}
        for name, value in datadict.items():
            if type(value) is str:
                columns[name] = "TEXT"
            elif type(value) is int:
                columns[name] = "INT"
            elif type(value) is datetime.datetime:
                columns[name] = "DATETIME"
            elif type(value) is Decimal:
                columns[name] = "DECIMAL"
            elif type(value) is float:
                columns[name] = "FLOAT"
        return columns

    def test_bulk_insert_rows(self):
        """Test that the bulk insert method inserts line items."""
        # Get data commited for foreign key relationships to work
        with schema_context(self.schema):

            table_name = AWS_CUR_TABLE_MAP["line_item"]
            query = self.accessor._get_db_obj_query(table_name)
            initial_count = query.count()
            cost_entry = query.first()

            data_dict = self.creator.create_columns_for_table(table_name)
            data_dict["cost_entry_bill_id"] = cost_entry.cost_entry_bill_id
            data_dict["cost_entry_id"] = cost_entry.cost_entry_id
            data_dict["cost_entry_product_id"] = cost_entry.cost_entry_product_id
            data_dict["cost_entry_pricing_id"] = cost_entry.cost_entry_pricing_id
            data_dict["cost_entry_reservation_id"] = cost_entry.cost_entry_reservation_id

            columns = list(data_dict.keys())
            values = list(data_dict.values())
            file_obj = self.creator.create_csv_file_stream(values)

            self.accessor.bulk_insert_rows(file_obj, table_name, columns)
            new_query = self.accessor._get_db_obj_query(table_name)

            new_count = new_query.count()
            new_line_item = new_query.order_by("-id").first()

            self.assertTrue(new_count > initial_count)
            for column in columns:
                value = getattr(new_line_item, column)
                if isinstance(value, datetime.datetime):
                    value = self.creator.stringify_datetime(value)
                    data_dict[column] = self.creator.stringify_datetime(data_dict[column])
                self.assertEqual(value, data_dict[column])

    def test_insert_on_conflict_do_nothing_with_conflict(self):
        """Test that an INSERT succeeds ignoring the conflicting row."""
        table_name = AWS_CUR_TABLE_MAP["product"]
        table = AWSCostEntryProduct
        with schema_context(self.schema):
            data = self.creator.create_columns_for_table(table_name)
            query = self.accessor._get_db_obj_query(table_name)

            initial_count = query.count()

            row_id = self.accessor.insert_on_conflict_do_nothing(table, data)

            insert_count = query.count()

            self.assertEqual(insert_count, initial_count + 1)

            row_id_2 = self.accessor.insert_on_conflict_do_nothing(table, data)

            self.assertEqual(insert_count, query.count())
            self.assertEqual(row_id, row_id_2)

    def test_insert_on_conflict_do_nothing_without_conflict(self):
        """Test that an INSERT succeeds inserting all non-conflicting rows."""
        # table_name = random.choice(self.foreign_key_tables)
        table_name = AWS_CUR_TABLE_MAP["product"]
        table = AWSCostEntryProduct

        data = [self.creator.create_columns_for_table(table_name), self.creator.create_columns_for_table(table_name)]
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            previous_count = query.count()
            previous_row_id = None
            for entry in data:
                row_id = self.accessor.insert_on_conflict_do_nothing(table, entry)
                count = query.count()

                self.assertEqual(count, previous_count + 1)
                self.assertNotEqual(row_id, previous_row_id)

                previous_count = count
                previous_row_id = row_id

    def test_insert_on_conflict_do_update_with_conflict(self):
        """Test that an INSERT succeeds ignoring the conflicting row."""
        table_name = AWS_CUR_TABLE_MAP["reservation"]
        table = AWSCostEntryReservation
        data = self.creator.create_columns_for_table(table_name)
        query = self.accessor._get_db_obj_query(table)
        with schema_context(self.schema):
            initial_res_count = 1
            initial_count = query.count()
            data["number_of_reservations"] = initial_res_count
            row_id = self.accessor.insert_on_conflict_do_update(
                table, data, conflict_columns=["reservation_arn"], set_columns=list(data.keys())
            )
            insert_count = query.count()
            row = query.order_by("-id").all()[0]
            self.assertEqual(insert_count, initial_count + 1)
            self.assertEqual(row.number_of_reservations, initial_res_count)

            data["number_of_reservations"] = initial_res_count + 1
            row_id_2 = self.accessor.insert_on_conflict_do_update(
                table, data, conflict_columns=["reservation_arn"], set_columns=list(data.keys())
            )
            row = query.filter(id=row_id_2).first()

            self.assertEqual(insert_count, query.count())
            self.assertEqual(row_id, row_id_2)
            self.assertEqual(row.number_of_reservations, initial_res_count + 1)

    def test_insert_on_conflict_do_update_without_conflict(self):
        """Test that an INSERT succeeds inserting all non-conflicting rows."""
        table_name = AWS_CUR_TABLE_MAP["reservation"]
        table = AWSCostEntryReservation

        data = [self.creator.create_columns_for_table(table_name), self.creator.create_columns_for_table(table_name)]
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            previous_count = query.count()
            previous_row_id = None
            for entry in data:
                row_id = self.accessor.insert_on_conflict_do_update(
                    table, entry, conflict_columns=["reservation_arn"], set_columns=list(entry.keys())
                )
                count = query.count()

                self.assertEqual(count, previous_count + 1)
                self.assertNotEqual(row_id, previous_row_id)

                previous_count = count
                previous_row_id = row_id

    def test_get_primary_key(self):
        """Test that a primary key is returned."""
        table_name = random.choice(self.foreign_key_tables)
        with schema_context(self.schema):
            data = self.creator.create_columns_for_table(table_name)
            if table_name == AWS_CUR_TABLE_MAP["bill"]:
                data["provider_id"] = self.aws_provider_uuid
            obj = self.accessor.create_db_object(table_name, data)
            obj.save()

            p_key = self.accessor._get_primary_key(table_name, data)

            self.assertIsNotNone(p_key)

    def test_get_primary_key_attribute_error(self):
        """Test that an AttributeError is raised on bad primary key lookup."""
        table_name = AWS_CUR_TABLE_MAP["product"]
        with schema_context(self.schema):
            data = self.creator.create_columns_for_table(table_name)
            obj = self.accessor.create_db_object(table_name, data)
            obj.save()

            data["sku"] = "".join([random.choice(string.digits) for _ in range(5)])
            with self.assertRaises(AttributeError):
                self.accessor._get_primary_key(table_name, data)

    def test_clean_data(self):
        """Test that data cleaning produces proper data types."""
        table_name = random.choice(self.all_tables)
        column_types = self.report_schema.column_types[table_name]

        data = self.creator.create_columns_for_table(table_name)
        cleaned_data = self.accessor.clean_data(data, table_name)

        for key, value in cleaned_data.items():
            column_type = column_types[key]
            type = map_django_field_type_to_python_type(column_type)
            self.assertIsInstance(value, type)

    def test_convert_value_decimal_invalid_operation(self):
        """Test that an InvalidOperation is raised and None is returned."""
        dec = Decimal("123342348239472398472309847230984723098427309")

        result = self.accessor._convert_value(dec, Decimal)
        self.assertIsNone(result)

        result = self.accessor._convert_value("", Decimal)
        self.assertIsNone(result)

    def test_convert_value_value_error(self):
        """Test that a value error results in a None value."""
        value = "Not a Number"
        result = self.accessor._convert_value(value, float)
        self.assertIsNone(result)

    def test_get_cost_entry_bills(self):
        """Test that bills are returned in a dict."""
        table_name = AWS_CUR_TABLE_MAP["bill"]
        with schema_context(self.schema):
            bill = self.accessor._get_db_obj_query(table_name).first()
            expected_key = (bill.bill_type, bill.payer_account_id, bill.billing_period_start, bill.provider_id)
            # expected = {expected_key: bill.id}

            bill_map = self.accessor.get_cost_entry_bills()
            self.assertIn(expected_key, bill_map)
            self.assertEqual(bill_map[expected_key], bill.id)

    def test_get_cost_entry_bills_by_date(self):
        """Test that get bills by date functions correctly."""
        table_name = AWS_CUR_TABLE_MAP["bill"]
        with schema_context(self.schema):
            today = datetime.datetime.utcnow()
            bill_start = today.replace(day=1).date()
            bill_id = self.accessor._get_db_obj_query(table_name).filter(billing_period_start=bill_start).first().id
            bills = self.accessor.get_cost_entry_bills_by_date(bill_start)
            self.assertEqual(bill_id, bills[0].id)

    def test_get_bill_query_before_date(self):
        """Test that gets a query for cost entry bills before a date."""
        with schema_context(self.schema):
            table_name = AWS_CUR_TABLE_MAP["bill"]
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
            self.assertEqual(cost_entries.count(), 2)
            self.assertEqual(cost_entries.first().billing_period_start, cutoff_date)

            # Verify that no results are returned for a date earlier than cutoff_date
            earlier_date = cutoff_date + relativedelta.relativedelta(months=-1)
            earlier_cutoff = earlier_date.replace(month=earlier_date.month, day=15)
            cost_entries = self.accessor.get_bill_query_before_date(earlier_cutoff)
            self.assertEqual(cost_entries.count(), 0)

    def test_get_lineitem_query_for_billid(self):
        """Test that gets a cost entry line item query given a bill id."""
        table_name = "reporting_awscostentrybill"
        with schema_context(self.schema):
            # Verify that the line items for the test bill_id are returned
            bill_id = self.accessor._get_db_obj_query(table_name).first().id
            line_item_query = self.accessor.get_lineitem_query_for_billid(bill_id)
            self.assertEqual(line_item_query.first().cost_entry_bill_id, bill_id)

            # Verify that no line items are returned for a missing bill_id
            wrong_bill_id = bill_id + 5
            line_item_query = self.accessor.get_lineitem_query_for_billid(wrong_bill_id)
            self.assertEqual(line_item_query.count(), 0)

    def test_get_cost_entry_query_for_billid(self):
        """Test that gets a cost entry query given a bill id."""
        table_name = "reporting_awscostentrybill"
        with schema_context(self.schema):
            # Verify that the line items for the test bill_id are returned
            bill_id = self.accessor._get_db_obj_query(table_name).first().id

            cost_entry_query = self.accessor.get_cost_entry_query_for_billid(bill_id)
            self.assertEqual(cost_entry_query.first().bill_id, bill_id)

            # Verify that no line items are returned for a missing bill_id
            wrong_bill_id = bill_id + 5
            cost_entry_query = self.accessor.get_cost_entry_query_for_billid(wrong_bill_id)
            self.assertEqual(cost_entry_query.count(), 0)

    def test_get_cost_entries(self):
        """Test that a dict of cost entries are returned."""
        table_name = "reporting_awscostentry"
        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(table_name)
            count = query.count()
            first_entry = query.first()
            cost_entries = self.accessor.get_cost_entries()
            self.assertIsInstance(cost_entries, dict)
            self.assertEqual(len(cost_entries.keys()), count)
            self.assertIn(first_entry.id, cost_entries.values())

    def test_get_products(self):
        """Test that a dict of products are returned."""
        table_name = "reporting_awscostentryproduct"
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            count = query.count()
            first_entry = query.first()
            products = self.accessor.get_products()

            self.assertIsInstance(products, dict)
            self.assertEqual(len(products.keys()), count)
            expected_key = (first_entry.sku, first_entry.product_name, first_entry.region)
            self.assertIn(expected_key, products)

    def test_get_pricing(self):
        """Test that a dict of pricing is returned."""
        table_name = "reporting_awscostentrypricing"
        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(table_name)
            count = query.count()
            first_entry = query.first()

            pricing = self.accessor.get_pricing()

            self.assertIsInstance(pricing, dict)
            self.assertEqual(len(pricing.keys()), count)
            self.assertIn(first_entry.id, pricing.values())

    def test_get_reservations(self):
        """Test that a dict of reservations are returned."""
        table_name = AWS_CUR_TABLE_MAP["reservation"]
        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(table_name)
            count = query.count()
            first_entry = query.first()

            reservations = self.accessor.get_reservations()

            self.assertIsInstance(reservations, dict)
            self.assertEqual(len(reservations.keys()), count)
            self.assertIn(first_entry.reservation_arn, reservations)

    def test_populate_line_item_daily_table(self):
        """Test that the daily table is populated."""
        ce_table_name = AWS_CUR_TABLE_MAP["cost_entry"]
        daily_table_name = AWS_CUR_TABLE_MAP["line_item_daily"]
        ce_table = getattr(self.accessor.report_schema, ce_table_name)
        daily_table = getattr(self.accessor.report_schema, daily_table_name)

        with schema_context(self.schema):
            bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
            bill_ids = [str(bill.id) for bill in bills.all()]

            ce_entry = ce_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = ce_entry["interval_start__min"]
            end_date = ce_entry["interval_start__max"]

            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

            query = self.accessor._get_db_obj_query(daily_table_name)
            query.delete()
            initial_count = query.count()

        self.accessor.populate_line_item_daily_table(start_date, end_date, bill_ids)

        with schema_context(self.schema):
            self.assertNotEqual(query.count(), initial_count)

            daily_entry = daily_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = daily_entry["usage_start__min"]
            result_end_date = daily_entry["usage_start__max"]

            self.assertEqual(result_start_date, start_date.date())
            self.assertEqual(result_end_date, end_date.date())
            entry = query.first()

            summary_columns = [
                "cost_entry_product_id",
                "cost_entry_pricing_id",
                "line_item_type",
                "usage_account_id",
                "usage_start",
                "usage_end",
                "product_code",
                "usage_type",
                "operation",
                "resource_id",
                "usage_amount",
                "currency_code",
                "unblended_rate",
                "unblended_cost",
                "blended_rate",
                "blended_cost",
                "public_on_demand_cost",
                "public_on_demand_rate",
                "tags",
            ]

            for column in summary_columns:
                self.assertIsNotNone(getattr(entry, column))

            self.assertNotEqual(getattr(entry, "tags"), {})

    def test_populate_line_item_daily_table_no_bill_ids(self):
        """Test that the daily table is populated."""
        ce_table_name = AWS_CUR_TABLE_MAP["cost_entry"]
        daily_table_name = AWS_CUR_TABLE_MAP["line_item_daily"]
        ce_table = getattr(self.accessor.report_schema, ce_table_name)
        daily_table = getattr(self.accessor.report_schema, daily_table_name)
        bill_ids = None

        with schema_context(self.schema):
            ce_entry = ce_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = ce_entry["interval_start__min"]
            end_date = ce_entry["interval_start__max"]

            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

            query = self.accessor._get_db_obj_query(daily_table_name)

        self.accessor.populate_line_item_daily_table(start_date, end_date, bill_ids)

        with schema_context(self.schema):
            daily_entry = daily_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = daily_entry["usage_start__min"]
            result_end_date = daily_entry["usage_start__max"]

            self.assertEqual(result_start_date, start_date.date())
            self.assertEqual(result_end_date, end_date.date())
            entry = query.first()

            summary_columns = [
                "cost_entry_product_id",
                "cost_entry_pricing_id",
                "line_item_type",
                "usage_account_id",
                "usage_start",
                "usage_end",
                "product_code",
                "usage_type",
                "operation",
                "resource_id",
                "usage_amount",
                "currency_code",
                "unblended_rate",
                "unblended_cost",
                "blended_rate",
                "blended_cost",
                "public_on_demand_cost",
                "public_on_demand_rate",
                "tags",
            ]
            for column in summary_columns:
                self.assertIsNotNone(getattr(entry, column))

            self.assertNotEqual(getattr(entry, "tags"), {})

    def test_populate_line_item_daily_summary_table(self):
        """Test that the daily summary table is populated."""
        ce_table_name = AWS_CUR_TABLE_MAP["cost_entry"]
        summary_table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]

        ce_table = getattr(self.accessor.report_schema, ce_table_name)
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        for _ in range(10):
            bill = self.creator.create_cost_entry_bill(provider_uuid=self.aws_provider.uuid)
            cost_entry = self.creator.create_cost_entry(bill)
            product = self.creator.create_cost_entry_product()
            pricing = self.creator.create_cost_entry_pricing()
            reservation = self.creator.create_cost_entry_reservation()
            self.creator.create_cost_entry_line_item(bill, cost_entry, product, pricing, reservation)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

        table_name = AWS_CUR_TABLE_MAP["line_item"]
        tag_query = self.accessor._get_db_obj_query(table_name)
        possible_keys = []
        possible_values = []
        with schema_context(self.schema):
            for item in tag_query:
                possible_keys += list(item.tags.keys())
                possible_values += list(item.tags.values())

            ce_entry = ce_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = ce_entry["interval_start__min"]
            end_date = ce_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_line_item_daily_table(start_date, end_date, bill_ids)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, bill_ids)
        with schema_context(self.schema):
            self.assertNotEqual(query.count(), initial_count)

            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = summary_entry["usage_start__min"]
            result_end_date = summary_entry["usage_start__max"]

            self.assertEqual(result_start_date, start_date.date())
            self.assertEqual(result_end_date, end_date.date())

            entry = query.order_by("-id")

            summary_columns = [
                "usage_start",
                "usage_end",
                "usage_account_id",
                "product_code",
                "product_family",
                "availability_zone",
                "region",
                "instance_type",
                "unit",
                "resource_count",
                "usage_amount",
                "normalization_factor",
                "normalized_usage_amount",
                "currency_code",
                "unblended_rate",
                "unblended_cost",
                "blended_rate",
                "blended_cost",
                "public_on_demand_cost",
                "public_on_demand_rate",
                "tags",
            ]

            for column in summary_columns:
                self.assertIsNotNone(getattr(entry.first(), column))

            found_keys = []
            found_values = []
            for item in query.all():
                found_keys += list(item.tags.keys())
                found_values += list(item.tags.values())

            self.assertEqual(set(sorted(possible_keys)), set(sorted(found_keys)))
            self.assertEqual(set(sorted(possible_values)), set(sorted(found_values)))

    def test_populate_line_item_daily_summary_table_no_bill_ids(self):
        """Test that the daily summary table is populated."""
        ce_table_name = AWS_CUR_TABLE_MAP["cost_entry"]
        summary_table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]

        ce_table = getattr(self.accessor.report_schema, ce_table_name)
        summary_table = getattr(self.accessor.report_schema, summary_table_name)
        bill_ids = None

        for _ in range(10):
            bill = self.creator.create_cost_entry_bill(provider_uuid=self.aws_provider.uuid)
            cost_entry = self.creator.create_cost_entry(bill)
            product = self.creator.create_cost_entry_product()
            pricing = self.creator.create_cost_entry_pricing()
            reservation = self.creator.create_cost_entry_reservation()
            self.creator.create_cost_entry_line_item(bill, cost_entry, product, pricing, reservation)

        table_name = AWS_CUR_TABLE_MAP["line_item"]
        tag_query = self.accessor._get_db_obj_query(table_name)
        possible_keys = []
        possible_values = []
        with schema_context(self.schema):
            for item in tag_query:
                possible_keys += list(item.tags.keys())
                possible_values += list(item.tags.values())

            ce_entry = ce_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = ce_entry["interval_start__min"]
            end_date = ce_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_line_item_daily_table(start_date, end_date, bill_ids)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, bill_ids)
        with schema_context(self.schema):
            self.assertNotEqual(query.count(), initial_count)

            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = summary_entry["usage_start__min"]
            result_end_date = summary_entry["usage_start__max"]

            self.assertEqual(result_start_date, start_date.date())
            self.assertEqual(result_end_date, end_date.date())

            entry = query.order_by("-id")

            summary_columns = [
                "usage_start",
                "usage_end",
                "usage_account_id",
                "product_code",
                "product_family",
                "availability_zone",
                "region",
                "instance_type",
                "unit",
                "resource_count",
                "usage_amount",
                "normalization_factor",
                "normalized_usage_amount",
                "currency_code",
                "unblended_rate",
                "unblended_cost",
                "blended_rate",
                "blended_cost",
                "public_on_demand_cost",
                "public_on_demand_rate",
                "tags",
            ]

            for column in summary_columns:
                self.assertIsNotNone(getattr(entry.first(), column))

            found_keys = []
            found_values = []
            for item in query.all():
                found_keys += list(item.tags.keys())
                found_values += list(item.tags.values())

            self.assertEqual(set(sorted(possible_keys)), set(sorted(found_keys)))
            self.assertEqual(set(sorted(possible_values)), set(sorted(found_values)))

    def test_populate_awstags_summary_table(self):
        """Test that the AWS tags summary table is populated."""
        tags_summary_name = AWS_CUR_TABLE_MAP["tags_summary"]

        query = self.accessor._get_db_obj_query(tags_summary_name)
        with schema_context(self.schema):
            tags = query.all()
            tag_keys = list({tag.key for tag in tags})

        with schema_context(self.schema):
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT DISTINCT jsonb_object_keys(tags)
                        FROM reporting_awscostentrylineitem_daily"""
                )
                expected_tag_keys = cursor.fetchall()
                expected_tag_keys = [tag[0] for tag in expected_tag_keys]

            self.assertEqual(sorted(tag_keys), sorted(expected_tag_keys))

    def test_populate_ocp_on_aws_cost_daily_summary(self):
        """Test that the OCP on AWS cost summary table is populated."""
        summary_table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_daily_summary"]
        project_summary_table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_project_daily_summary"]
        bill_ids = []
        markup_value = Decimal(0.1)

        summary_table = getattr(self.accessor.report_schema, summary_table_name)
        project_table = getattr(self.accessor.report_schema, project_summary_table_name)

        today = DateAccessor().today_with_timezone("UTC")
        last_month = today - relativedelta.relativedelta(months=1)
        resource_id = "i-12345"
        with schema_context(self.schema):
            for cost_entry_date in (today, last_month):
                bill = self.creator.create_cost_entry_bill(
                    provider_uuid=self.aws_provider.uuid, bill_date=cost_entry_date
                )
                bill_ids.append(str(bill.id))
                cost_entry = self.creator.create_cost_entry(bill, cost_entry_date)
                product = self.creator.create_cost_entry_product("Compute Instance")
                pricing = self.creator.create_cost_entry_pricing()
                reservation = self.creator.create_cost_entry_reservation()
                self.creator.create_cost_entry_line_item(
                    bill, cost_entry, product, pricing, reservation, resource_id=resource_id
                )

        self.accessor.populate_line_item_daily_table(last_month, today, bill_ids)

        li_table_name = AWS_CUR_TABLE_MAP["line_item"]
        with schema_context(self.schema):
            li_table = getattr(self.accessor.report_schema, li_table_name)

            sum_aws_cost = li_table.objects.all().aggregate(Sum("unblended_cost"))["unblended_cost__sum"]

        with OCPReportDBAccessor(self.schema) as ocp_accessor:
            cluster_id = "testcluster"
            with ProviderDBAccessor(provider_uuid=self.ocp_test_provider_uuid) as provider_access:
                provider_uuid = provider_access.get_provider().uuid

            for cost_entry_date in (today, last_month):
                period = self.creator.create_ocp_report_period(
                    provider_uuid, period_date=cost_entry_date, cluster_id=cluster_id
                )
                report = self.creator.create_ocp_report(period, cost_entry_date)
                self.creator.create_ocp_usage_line_item(period, report, resource_id=resource_id)
                self.creator.create_ocp_node_label_line_item(period, report)

            ocp_report_table_name = OCP_REPORT_TABLE_MAP["report"]
            with schema_context(self.schema):
                report_table = getattr(ocp_accessor.report_schema, ocp_report_table_name)

                report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
                start_date = report_entry["interval_start__min"]
                end_date = report_entry["interval_start__max"]

                start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

            ocp_accessor.populate_node_label_line_item_daily_table(start_date, end_date, cluster_id)
            ocp_accessor.populate_line_item_daily_table(start_date, end_date, cluster_id)
            ocp_accessor.populate_line_item_daily_summary_table(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(summary_table_name)
            initial_count = query.count()

        self.accessor.populate_ocp_on_aws_cost_daily_summary(last_month, today, cluster_id, bill_ids, markup_value)
        with schema_context(self.schema):
            self.assertNotEqual(query.count(), initial_count)

            sum_cost = summary_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("unblended_cost"))[
                "unblended_cost__sum"
            ]
            sum_project_cost = project_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("unblended_cost"))[
                "unblended_cost__sum"
            ]
            sum_pod_cost = project_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("pod_cost"))[
                "pod_cost__sum"
            ]
            sum_markup_cost = summary_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("markup_cost"))[
                "markup_cost__sum"
            ]
            sum_markup_cost_project = project_table.objects.filter(cluster_id=cluster_id).aggregate(
                Sum("markup_cost")
            )["markup_cost__sum"]
            sum_project_markup_cost_project = project_table.objects.filter(cluster_id=cluster_id).aggregate(
                Sum("project_markup_cost")
            )["project_markup_cost__sum"]

            self.assertEqual(sum_cost, sum_project_cost)
            self.assertLessEqual(sum_cost, sum_aws_cost)
            self.assertAlmostEqual(sum_markup_cost, sum_cost * markup_value, 9)
            self.assertAlmostEqual(sum_markup_cost_project, sum_cost * markup_value, 9)
            self.assertAlmostEqual(sum_project_markup_cost_project, sum_pod_cost * markup_value, 9)

    def test_bills_for_provider_uuid(self):
        """Test that bills_for_provider_uuid returns the right bills."""
        bill1_date = datetime.datetime(2018, 1, 6, 0, 0, 0)
        bill2_date = datetime.datetime(2018, 2, 3, 0, 0, 0)

        self.creator.create_cost_entry_bill(bill_date=bill1_date, provider_uuid=self.aws_provider.uuid)
        bill2 = self.creator.create_cost_entry_bill(provider_uuid=self.aws_provider.uuid, bill_date=bill2_date)

        bills = self.accessor.bills_for_provider_uuid(
            self.aws_provider.uuid, start_date=bill2_date.strftime("%Y-%m-%d")
        )
        with schema_context(self.schema):
            self.assertEquals(len(bills), 1)
            self.assertEquals(bills[0].id, bill2.id)

    def test_mark_bill_as_finalized(self):
        """Test that test_mark_bill_as_finalized sets finalized_datetime field."""
        bill = self.creator.create_cost_entry_bill(provider_uuid=self.aws_provider.uuid)
        with schema_context(self.schema):
            self.assertIsNone(bill.finalized_datetime)
            self.accessor.mark_bill_as_finalized(bill.id)
            bill.refresh_from_db()
            self.assertIsNotNone(bill.finalized_datetime)

    def test_populate_markup_cost(self):
        """Test that the daily summary table is populated."""
        summary_table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            expected_markup = query.filter(cost_entry_bill__in=bill_ids).aggregate(
                markup=Sum(F("unblended_cost") * decimal.Decimal(0.1))
            )
            expected_markup = expected_markup.get("markup")

        self.accessor.populate_markup_cost(0.1, bill_ids)
        with schema_context(self.schema):
            query = (
                self.accessor._get_db_obj_query(summary_table_name)
                .filter(cost_entry_bill__in=bill_ids)
                .aggregate(Sum("markup_cost"))
            )
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    def test_populate_markup_cost_no_billsids(self):
        """Test that the daily summary table is populated."""
        summary_table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            expected_markup = query.aggregate(markup=Sum(F("unblended_cost") * decimal.Decimal(0.1)))
            expected_markup = expected_markup.get("markup")

        self.accessor.populate_markup_cost(0.1, None)
        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(summary_table_name).aggregate(Sum("markup_cost"))
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)
