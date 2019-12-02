#
# Copyright 2019 Red Hat, Inc.
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

"""Test the AzureReportDBAccessor utility object."""
import datetime
import decimal
from tenant_schemas.utils import schema_context

from unittest.mock import patch

from django.db.models import Max, Min

from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


class AzureReportDBAccessorTest(MasuTestCase):
    """Test Cases for the AzureReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = AzureReportDBAccessor(
            schema=cls.schema, column_map=cls.column_map
        )
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)

        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AZURE_REPORT_TABLE_MAP['bill'],
            AZURE_REPORT_TABLE_MAP['product'],
            AZURE_REPORT_TABLE_MAP['meter'],
        ]
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        today = DateAccessor().today_with_timezone('UTC')
        billing_start = today.replace(day=1)

        self.manifest_dict = {
            'assembly_id': '1234',
            'billing_period_start_datetime': billing_start,
            'num_total_files': 2,
            'provider_uuid': self.azure_provider_uuid,
        }

        bill = self.creator.create_azure_cost_entry_bill(
            provider_uuid=self.azure_provider_uuid, bill_date=today
        )
        product = self.creator.create_azure_cost_entry_product(
            provider_uuid=self.azure_provider_uuid
        )
        meter = self.creator.create_azure_meter(provider_uuid=self.azure_provider_uuid)
        self.creator.create_azure_cost_entry_line_item(bill, product, meter)
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)

    def test_get_cost_entry_bills(self):
        """Test that Azure bills are returned in a dict."""
        table_name = AZURE_REPORT_TABLE_MAP['bill']
        with schema_context(self.schema):
            bill = self.accessor._get_db_obj_query(table_name).first()
            expected_key = (bill.billing_period_start, bill.provider_id)
            bill_map = self.accessor.get_cost_entry_bills()
            self.assertIn(expected_key, bill_map)
            self.assertEqual(bill_map[expected_key], bill.id)

    def test_get_products(self):
        """Test that a dict of Azure products are returned."""
        table_name = AZURE_REPORT_TABLE_MAP['product']
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            count = query.count()
            first_entry = query.first()
            products = self.accessor.get_products()

            self.assertIsInstance(products, dict)
            self.assertEqual(len(products.keys()), count)
            expected_key = (
                first_entry.instance_id,
                first_entry.service_name,
                first_entry.service_tier,
            )
            self.assertIn(expected_key, products)

    def test_get_meters(self):
        """Test that a dict of Azure meters are returned."""
        table_name = AZURE_REPORT_TABLE_MAP['meter']
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            count = query.count()
            first_entry = query.first()
            meters = self.accessor.get_meters()

            self.assertIsInstance(meters, dict)
            self.assertEqual(len(meters.keys()), count)
            expected_key = first_entry.meter_id
            self.assertIn(expected_key, meters)

    def test_bills_for_provider_uuid(self):
        """Test that bills_for_provider_uuid returns the right bills."""
        bill1_date = datetime.datetime(2018, 1, 6, 0, 0, 0)
        bill2_date = datetime.datetime(2018, 2, 3, 0, 0, 0)

        self.creator.create_azure_cost_entry_bill(
            bill_date=bill1_date, provider_uuid=self.azure_provider_uuid
        )
        bill2 = self.creator.create_azure_cost_entry_bill(
            provider_uuid=self.azure_provider_uuid, bill_date=bill2_date
        )

        bills = self.accessor.bills_for_provider_uuid(
            self.azure_provider_uuid, start_date=bill2_date.strftime('%Y-%m-%d')
        )
        with schema_context(self.schema):
            self.assertEquals(len(bills), 1)
            self.assertEquals(bills[0].id, bill2.id)

    def test_populate_line_item_daily_summary_table(self):
        """Test that the daily summary table is populated."""
        summary_table_name = AZURE_REPORT_TABLE_MAP['line_item_daily_summary']
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        for _ in range(10):
            bill = self.creator.create_azure_cost_entry_bill(
                provider_uuid=self.azure_provider_uuid
            )
            product = self.creator.create_azure_cost_entry_product(
                provider_uuid=self.azure_provider_uuid
            )
            meter = self.creator.create_azure_meter(
                provider_uuid=self.azure_provider_uuid
            )
            self.creator.create_azure_cost_entry_line_item(bill, product, meter)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(
            self.azure_provider_uuid
        )
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

        table_name = AZURE_REPORT_TABLE_MAP['line_item']
        line_item_table = getattr(self.accessor.report_schema, table_name)
        tag_query = self.accessor._get_db_obj_query(table_name)
        possible_keys = []
        possible_values = []
        with schema_context(self.schema):
            for item in tag_query:
                possible_keys += list(item.tags.keys())
                possible_values += list(item.tags.values())

            li_entry = line_item_table.objects.all().aggregate(
                Min('usage_date_time'), Max('usage_date_time')
            )
            start_date = li_entry['usage_date_time__min']
            end_date = li_entry['usage_date_time__max']

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_line_item_daily_summary_table(
            start_date, end_date, bill_ids
        )
        with schema_context(self.schema):
            self.assertNotEqual(query.count(), initial_count)

            summary_entry = summary_table.objects.all().aggregate(
                Min('usage_start'), Max('usage_start')
            )
            result_start_date = summary_entry['usage_start__min']
            result_end_date = summary_entry['usage_start__max']

            self.assertEqual(result_start_date, start_date)
            self.assertEqual(result_end_date, end_date)

            entry = query.order_by('-id')

            summary_columns = [
                'usage_start',
                'usage_quantity',
                'pretax_cost',
                'offer_id',
                'cost_entry_bill_id',
                'meter_id',
                'tags',
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

    def test_get_cost_entry_bills_by_date(self):
        """Test that get bills by date functions correctly."""
        table_name = AZURE_REPORT_TABLE_MAP['bill']
        with schema_context(self.schema):
            today = datetime.datetime.utcnow()
            bill_start = today.replace(day=1).date()
            bill_id = self.accessor._get_db_obj_query(table_name).first().id
            bills = self.accessor.get_cost_entry_bills_by_date(bill_start)
            self.assertEqual(bill_id, bills[0].id)

    def test_populate_markup_cost(self):
        """Test that the daily summary table is populated."""
        summary_table_name = AZURE_REPORT_TABLE_MAP['line_item_daily_summary']

        bill = self.creator.create_azure_cost_entry_bill(
            provider_uuid=self.azure_provider_uuid
        )
        product = self.creator.create_azure_cost_entry_product(
            provider_uuid=self.azure_provider_uuid
        )
        meter = self.creator.create_azure_meter(provider_uuid=self.azure_provider_uuid)
        self.creator.create_azure_cost_entry_line_item(bill, product, meter)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(
            self.azure_provider_uuid
        )
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

        table_name = AZURE_REPORT_TABLE_MAP['line_item']
        line_item_table = getattr(self.accessor.report_schema, table_name)
        tag_query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            possible_value = tag_query[0].pretax_cost * decimal.Decimal(0.1)

            li_entry = line_item_table.objects.all().aggregate(
                Min('usage_date_time'), Max('usage_date_time')
            )
            start_date = li_entry['usage_date_time__min']
            end_date = li_entry['usage_date_time__max']

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(summary_table_name)

        self.accessor.populate_line_item_daily_summary_table(
            start_date, end_date, bill_ids
        )
        self.accessor.populate_markup_cost(0.1, bill_ids)
        with schema_context(self.schema):

            found_value = query[0].markup_cost

            self.assertAlmostEqual(found_value, possible_value, 6)

    def test_populate_markup_cost_no_billsids(self):
        """Test that the daily summary table is populated."""
        summary_table_name = AZURE_REPORT_TABLE_MAP['line_item_daily_summary']

        bill = self.creator.create_azure_cost_entry_bill(
            provider_uuid=self.azure_provider_uuid
        )
        product = self.creator.create_azure_cost_entry_product(
            provider_uuid=self.azure_provider_uuid
        )
        meter = self.creator.create_azure_meter(provider_uuid=self.azure_provider_uuid)
        self.creator.create_azure_cost_entry_line_item(bill, product, meter)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(
            self.azure_provider_uuid
        )
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

        table_name = AZURE_REPORT_TABLE_MAP['line_item']
        line_item_table = getattr(self.accessor.report_schema, table_name)
        tag_query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            possible_values = {}
            for item in tag_query:
                possible_values.update(
                    {item.cost_entry_bill_id: item.pretax_cost * decimal.Decimal(0.1)}
                )

            li_entry = line_item_table.objects.all().aggregate(
                Min('usage_date_time'), Max('usage_date_time')
            )
            start_date = li_entry['usage_date_time__min']
            end_date = li_entry['usage_date_time__max']

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(summary_table_name)

        self.accessor.populate_line_item_daily_summary_table(
            start_date, end_date, bill_ids
        )
        self.accessor.populate_markup_cost(0.1, None)
        with schema_context(self.schema):
            found_values = {}
            for item in query:
                found_values.update({item.cost_entry_bill_id: item.markup_cost})

        for k, v in found_values.items():
            self.assertAlmostEqual(v, possible_values[k], 6)
