#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSReportDBAccessor utility object."""
import datetime
import decimal
import os
import random
import string
from decimal import Decimal
from unittest.mock import patch

import django.apps
from dateutil import relativedelta
from django.conf import settings
from django.db import connection
from django.db import OperationalError
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from django.db.models.query import QuerySet
from django.db.utils import ProgrammingError
from psycopg2.errors import DeadlockDetected
from tenant_schemas.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.utils import DateHelper
from koku.database import get_model
from koku.database_exc import ExtendedDBException
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_db_accessor_base import ReportSchema
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import map_django_field_type_to_python_type
from masu.test.database.helpers import ReportObjectCreator
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.aws.models import AWSTagsSummary
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummary
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

    def test_exec_raw_sql_query(self):
        class _db:
            def set_schema(*args, **kwargs):
                return None

        class _crsr:
            def __init__(self, *args, **kwargs):
                self.db = _db()

            def __enter__(self, *args, **kwargs):
                return self

            def __exit__(self, *args, **kwargs):
                pass

            def execute(self, *args, **kwargs):
                try:
                    self.dd_exc = DeadlockDetected(
                        "deadlock detected"
                        + os.linesep
                        + "DETAIL: Process 88  transaction 34  blocked by process 99"
                        + os.linesep
                        + "Process 99  transaction 78  blocked by process 88"
                        + os.linesep
                    )
                    raise self.dd_exc
                except DeadlockDetected:
                    raise OperationalError(
                        "deadlock detected"
                        + os.linesep
                        + "DETAIL: Process 88  transaction 34  blocked by process 99"
                        + os.linesep
                        + "Process 99  transaction 78  blocked by process 88"
                        + os.linesep
                    )

        with patch("masu.database.report_db_accessor_base.connection.cursor", return_value=_crsr()):
            with self.assertRaises(ExtendedDBException):
                self.accessor._execute_raw_sql_query(None, None)


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
            table = get_model(table_name)

            query = self.accessor._get_db_obj_query(table_name)
            initial_count = query.count()
            cost_entry = query.first()

            data = {
                "cost_entry_bill__id": cost_entry.cost_entry_bill_id,
                "cost_entry__id": cost_entry.cost_entry_id,
                "cost_entry_product__id": cost_entry.cost_entry_product_id,
                "cost_entry_pricing__id": cost_entry.cost_entry_pricing_id,
                "cost_entry_reservation__id": cost_entry.cost_entry_reservation_id,
            }
            data_dict = self.creator.create_columns_for_table_with_bakery(table, data)

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
        table = get_model(table_name)
        with schema_context(self.schema):
            data = self.creator.create_columns_for_table_with_bakery(table)
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
        table = get_model(table_name)

        data = [
            self.creator.create_columns_for_table_with_bakery(table),
            self.creator.create_columns_for_table_with_bakery(table),
        ]
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
        table = get_model(table_name)
        data = self.creator.create_columns_for_table_with_bakery(table)
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
        table = get_model(table_name)

        data = [
            self.creator.create_columns_for_table_with_bakery(table),
            self.creator.create_columns_for_table_with_bakery(table),
        ]
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
        table = get_model(table_name)
        with schema_context(self.schema):
            data = self.creator.create_columns_for_table_with_bakery(table)
            if table_name == AWS_CUR_TABLE_MAP["bill"]:
                data["provider_id"] = self.aws_provider_uuid
            obj = self.accessor.create_db_object(table_name, data)
            obj.save()

            p_key = self.accessor._get_primary_key(table_name, data)

            self.assertIsNotNone(p_key)

    def test_get_primary_key_attribute_error(self):
        """Test that an AttributeError is raised on bad primary key lookup."""
        table_name = AWS_CUR_TABLE_MAP["product"]
        table = get_model(table_name)
        with schema_context(self.schema):
            data = self.creator.create_columns_for_table_with_bakery(table)
            obj = self.accessor.create_db_object(table_name, data)
            obj.save()

            data["sku"] = "".join(random.choice(string.digits) for _ in range(5))
            with self.assertRaises(AttributeError):
                self.accessor._get_primary_key(table_name, data)

    def test_clean_data(self):
        """Test that data cleaning produces proper data types."""
        table_name = random.choice(self.all_tables)
        table = get_model(table_name)
        column_types = self.report_schema.column_types[table_name]

        data = self.creator.create_columns_for_table_with_bakery(table)
        cleaned_data = self.accessor.clean_data(data, table_name)

        for key, value in cleaned_data.items():
            if key not in column_types:
                continue
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
            summary_table.objects.all().delete()
            initial_count = query.count()

        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, bill_ids)
        with schema_context(self.schema):
            self.assertNotEqual(query.count(), initial_count)

            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = summary_entry["usage_start__min"]
            result_end_date = summary_entry["usage_start__max"]

            self.assertEqual(result_start_date, start_date.date())
            self.assertEqual(result_end_date, end_date.date())

            entry = query.first()

            summary_columns = [
                "usage_start",
                "usage_end",
                "usage_account_id",
                "product_code",
                "product_family",
                "region",
                "unit",
                "resource_count",
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
            summary_table.objects.all().delete()
            initial_count = query.count()

        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, bill_ids)
        with schema_context(self.schema):
            self.assertNotEqual(query.count(), initial_count)

            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = summary_entry["usage_start__min"]
            result_end_date = summary_entry["usage_start__max"]

            self.assertEqual(result_start_date, start_date.date())
            self.assertEqual(result_end_date, end_date.date())

            entry = query.first()

            summary_columns = [
                "usage_start",
                "usage_end",
                "usage_account_id",
                "product_code",
                "product_family",
                "region",
                "unit",
                "resource_count",
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

        summary_table = get_model(summary_table_name)
        project_table = get_model(project_summary_table_name)

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
            li_table = get_model(li_table_name)

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
            ocp_accessor.populate_line_item_daily_summary_table(start_date, end_date, cluster_id, provider_uuid)
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
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            start_date = summary_entry["usage_start__min"]
            end_date = summary_entry["usage_start__max"]

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            expected_markup = query.filter(cost_entry_bill__in=bill_ids).aggregate(
                markup=Sum(F("unblended_cost") * decimal.Decimal(0.1))
            )
            expected_markup = expected_markup.get("markup")

        self.accessor.populate_markup_cost(self.aws_provider.uuid, 0.1, start_date, end_date, bill_ids)
        with schema_context(self.schema):
            query = (
                self.accessor._get_db_obj_query(summary_table_name)
                .filter(cost_entry_bill__in=bill_ids)
                .aggregate(Sum("markup_cost"))
            )
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_presto_raw_sql_query")
    def test_populate_line_item_daily_summary_table_presto(self, mock_presto):
        """Test that we construst our SQL and query using Presto."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_line_item_daily_summary_table_presto(
            start_date, end_date, self.aws_provider_uuid, current_bill_id, markup_value
        )
        mock_presto.assert_called()

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.delete_ocp_on_aws_hive_partition_by_day")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_presto_multipart_sql_query")
    def test_populate_ocp_on_aws_cost_daily_summary_presto(self, mock_presto, mock_delete):
        """Test that we construst our SQL and query using Presto."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = cost_model_accessor.distribution

        self.accessor.populate_ocp_on_aws_cost_daily_summary_presto(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.aws_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_presto.assert_called()

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.delete_ocp_on_aws_hive_partition_by_day")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_presto_multipart_sql_query")
    def test_populate_ocp_on_aws_cost_daily_summary_presto_memory_distribution(self, mock_presto, mock_delete):
        """Test that we construst our SQL and query using Presto."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = "memory"

        self.accessor.populate_ocp_on_aws_cost_daily_summary_presto(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.aws_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_presto.assert_called()

    @patch("masu.database.report_db_accessor_base.kpdb.connect")
    def test_execute_presto_raw_sql_query(self, mock_connect):
        """Test the presto execute method."""
        mock_sql = "SELECT number FROM table"
        mock_result = [[1], [2]]
        mock_connect.return_value.cursor.return_value.fetchall.return_value = mock_result

        result = self.accessor._execute_presto_raw_sql_query(self.schema, mock_sql)

        self.assertEqual(result, mock_result)

    @patch("masu.database.report_db_accessor_base.kpdb.connect")
    def test_execute_presto_multipart_sql_query(self, mock_connect):
        """Test the presto execute method."""
        mock_sql = "SELECT number FROM table; SELECT other_number FROM other_table;"
        mock_result = [[1], [2]]
        mock_connect.return_value.cursor.return_value.fetchall.return_value = mock_result
        expected = mock_result + mock_result

        result = self.accessor._execute_presto_multipart_sql_query(self.schema, mock_sql)

        self.assertEqual(result, expected)

    def test_populate_enabled_tag_keys(self):
        """Test that enabled tag keys are populated."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.aws_provider_uuid, start_date)
        with schema_context(self.schema):
            AWSTagsSummary.objects.all().delete()
            AWSEnabledTagKeys.objects.all().delete()
            bill_ids = [bill.id for bill in bills]
            self.assertEqual(AWSEnabledTagKeys.objects.count(), 0)
            self.accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            self.assertNotEqual(AWSEnabledTagKeys.objects.count(), 0)

    def test_update_line_item_daily_summary_with_enabled_tags(self):
        """Test that we filter the daily summary table's tags with only enabled tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.aws_provider_uuid, start_date)
        with schema_context(self.schema):
            AWSTagsSummary.objects.all().delete()
            key_to_keep = AWSEnabledTagKeys.objects.first()
            AWSEnabledTagKeys.objects.exclude(key=key_to_keep.key).delete()
            bill_ids = [bill.id for bill in bills]
            self.accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, bill_ids)
            tags = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, cost_entry_bill_id__in=bill_ids
                )
                .values_list("tags")
                .distinct()
            )

            for tag in tags:
                tag_dict = tag[0]
                tag_keys = list(tag_dict.keys())
                if tag_keys:
                    self.assertEqual([key_to_keep.key], tag_keys)
                else:
                    self.assertEqual([], tag_keys)

    def test_delete_line_item_daily_summary_entries_for_date_range(self):
        """Test that daily summary rows are deleted."""
        with schema_context(self.schema):
            start_date = AWSCostEntryLineItemDailySummary.objects.aggregate(Max("usage_start")).get("usage_start__max")
            end_date = start_date

        table_query = AWSCostEntryLineItemDailySummary.objects.filter(
            source_uuid=self.aws_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
        )
        with schema_context(self.schema):
            self.assertNotEqual(table_query.count(), 0)

        self.accessor.delete_line_item_daily_summary_entries_for_date_range(
            self.aws_provider_uuid, start_date, end_date
        )

        with schema_context(self.schema):
            self.assertEqual(table_query.count(), 0)

    def test_delete_line_item_daily_summary_entries_for_date_range_with_filter(self):
        """Test that daily summary rows are deleted."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        new_cluster_id = "new_cluster_id"

        with schema_context(self.schema):
            cluster_ids = OCPAWSCostLineItemProjectDailySummary.objects.values_list("cluster_id").distinct()
            cluster_ids = [cluster_id[0] for cluster_id in cluster_ids]

            table_query = OCPAWSCostLineItemProjectDailySummary.objects.filter(
                source_uuid=self.aws_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
            )
            row_count = table_query.count()

            # Change the cluster on some rows
            update_uuids = table_query.values_list("uuid")[0 : round(row_count / 2, 2)]  # noqa: E203
            table_query.filter(uuid__in=update_uuids).update(cluster_id=new_cluster_id)

            self.assertNotEqual(row_count, 0)

        self.accessor.delete_line_item_daily_summary_entries_for_date_range(
            self.aws_provider_uuid,
            start_date,
            end_date,
            table=OCPAWSCostLineItemProjectDailySummary,
            filters={"cluster_id": cluster_ids[0]},
        )

        with schema_context(self.schema):
            # Make sure we didn't delete everything
            table_query = OCPAWSCostLineItemProjectDailySummary.objects.filter(
                source_uuid=self.aws_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
            )
            self.assertNotEqual(table_query.count(), 0)

            # Make sure we didn't delete this cluster
            table_query = OCPAWSCostLineItemProjectDailySummary.objects.filter(
                source_uuid=self.aws_provider_uuid,
                usage_start__gte=start_date,
                usage_start__lte=end_date,
                cluster_id=new_cluster_id,
            )
            self.assertNotEqual(table_query.count(), 0)

            # Make sure we deleted this cluster
            table_query = OCPAWSCostLineItemProjectDailySummary.objects.filter(
                source_uuid=self.aws_provider_uuid,
                usage_start__gte=start_date,
                usage_start__lte=end_date,
                cluster_id=cluster_ids[0],
            )
            self.assertEqual(table_query.count(), 0)

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, get_model("AWSCostEntryLineItemDailySummary"))
        self.assertEqual(self.accessor.line_item_table, get_model("AWSCostEntryLineItem"))
        self.assertEqual(self.accessor.cost_entry_table, get_model("AWSCostEntry"))
        self.assertEqual(self.accessor.line_item_daily_table, get_model("AWSCostEntryLineItemDaily"))

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, AWS_CUR_TABLE_MAP)

    def test_get_openshift_on_cloud_matched_tags(self):
        """Test that matched tags are returned."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()

        with schema_context(self.schema_name):
            bills = self.accessor.bills_for_provider_uuid(self.aws_provider_uuid, start_date)
            bill_id = bills.first().id

        with OCPReportDBAccessor(self.schema_name) as accessor:
            with schema_context(self.schema_name):
                report_period = accessor.report_periods_for_provider_uuid(
                    self.ocp_on_aws_ocp_provider.uuid, start_date
                )
                report_period_id = report_period.id

        matched_tags = self.accessor.get_openshift_on_cloud_matched_tags(bill_id, report_period_id)

        self.assertGreater(len(matched_tags), 0)
        self.assertIsInstance(matched_tags[0], dict)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_presto_raw_sql_query")
    def test_get_openshift_on_cloud_matched_tags_trino(self, mock_presto):
        """Test that Trino is used to find matched tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        self.accessor.get_openshift_on_cloud_matched_tags_trino(
            self.aws_provider_uuid, self.ocp_on_aws_ocp_provider.uuid, start_date, end_date
        )
        mock_presto.assert_called()

    def test_bad_sql_execution(self):
        script_file_name = "reporting_ocpallcostlineitem_project_daily_summary_aws.sql"
        script_file_path = f"{OCPReportDBAccessor.OCP_ON_ALL_SQL_PATH}{script_file_name}"
        with OCPReportDBAccessor(self.schema_name) as accessor:
            with self.assertRaises(ProgrammingError):
                accessor._execute_processing_script("masu.database", script_file_path, {})

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.table_exists_trino")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_presto_raw_sql_query")
    def test_delete_ocp_on_aws_hive_partition_by_day(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with self.assertRaises(TrinoExternalError):
            self.accessor.delete_ocp_on_aws_hive_partition_by_day(
                [1], self.aws_provider_uuid, self.ocp_provider_uuid, "2022", "01"
            )
        mock_trino.assert_called()
        self.assertEqual(mock_trino.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)
