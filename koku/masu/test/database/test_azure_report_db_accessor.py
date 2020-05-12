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

from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.util.azure.common import get_bills_from_provider


class AzureReportDBAccessorTest(MasuTestCase):
    """Test Cases for the AzureReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = AzureReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema)
        cls.dh = DateHelper()

        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AZURE_REPORT_TABLE_MAP["bill"],
            AZURE_REPORT_TABLE_MAP["product"],
            AZURE_REPORT_TABLE_MAP["meter"],
        ]
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

        today = self.dh.today
        billing_start = today.replace(day=1)

        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.azure_provider_uuid,
        }

    def test_get_cost_entry_bills(self):
        """Test that Azure bills are returned in a dict."""
        table_name = AZURE_REPORT_TABLE_MAP["bill"]
        with schema_context(self.schema):
            bill = self.accessor._get_db_obj_query(table_name).first()
            expected_key = (bill.billing_period_start, bill.provider_id)
            bill_map = self.accessor.get_cost_entry_bills()
            self.assertIn(expected_key, bill_map)
            self.assertEqual(bill_map[expected_key], bill.id)

    def test_get_products(self):
        """Test that a dict of Azure products are returned."""
        table_name = AZURE_REPORT_TABLE_MAP["product"]
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            count = query.count()
            first_entry = query.first()
            products = self.accessor.get_products()

            self.assertIsInstance(products, dict)
            self.assertEqual(len(products.keys()), count)
            expected_key = (
                first_entry.instance_id,
                first_entry.instance_type,
                first_entry.service_tier,
                first_entry.service_name,
            )
            self.assertIn(expected_key, products)

    def test_get_meters(self):
        """Test that a dict of Azure meters are returned."""
        table_name = AZURE_REPORT_TABLE_MAP["meter"]
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
        bills = self.accessor.bills_for_provider_uuid(self.azure_provider_uuid, start_date=self.dh.this_month_start)
        with schema_context(self.schema):
            self.assertEquals(len(bills), 1)

    def test_populate_line_item_daily_summary_table(self):
        """Test that the daily summary table is populated."""
        summary_table_name = AZURE_REPORT_TABLE_MAP["line_item_daily_summary"]
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider_uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

        table_name = AZURE_REPORT_TABLE_MAP["line_item"]
        line_item_table = getattr(self.accessor.report_schema, table_name)
        tag_query = self.accessor._get_db_obj_query(table_name)
        possible_keys = []
        possible_values = []
        with schema_context(self.schema):
            for item in tag_query:
                possible_keys += list(item.tags.keys())
                possible_values += list(item.tags.values())

            li_entry = line_item_table.objects.all().aggregate(Min("usage_date"), Max("usage_date"))
            start_date = li_entry["usage_date__min"]
            end_date = li_entry["usage_date__max"]

        start_date = start_date.date() if isinstance(start_date, datetime.datetime) else start_date
        end_date = end_date.date() if isinstance(end_date, datetime.datetime) else end_date

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            query.delete()
            initial_count = query.count()

        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, bill_ids)
        with schema_context(self.schema):
            self.assertNotEqual(query.count(), initial_count)

            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = summary_entry["usage_start__min"]
            result_end_date = summary_entry["usage_start__max"]

            self.assertEqual(result_start_date, start_date)
            self.assertEqual(result_end_date, end_date)

            entry = query.order_by("-id")

            summary_columns = [
                "usage_start",
                "usage_quantity",
                "pretax_cost",
                "cost_entry_bill_id",
                "meter_id",
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

    def test_get_cost_entry_bills_by_date(self):
        """Test that get bills by date functions correctly."""
        table_name = AZURE_REPORT_TABLE_MAP["bill"]
        with schema_context(self.schema):
            today = datetime.datetime.utcnow()
            bill_start = today.replace(day=1).date()
            bill_count = (
                self.accessor._get_db_obj_query(table_name)
                .filter(billing_period_start=self.dh.this_month_start)
                .count()
            )
            bills = self.accessor.get_cost_entry_bills_by_date(bill_start)
            self.assertEqual(bills.count(), bill_count)

    def test_populate_markup_cost(self):
        """Test that the daily summary table is populated."""
        summary_table_name = AZURE_REPORT_TABLE_MAP["line_item_daily_summary"]

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider_uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            expected_markup = query.filter(cost_entry_bill__in=bill_ids).aggregate(
                markup=Sum(F("pretax_cost") * decimal.Decimal(0.1))
            )
            expected_markup = expected_markup.get("markup")

        query = self.accessor._get_db_obj_query(summary_table_name)

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
        summary_table_name = AZURE_REPORT_TABLE_MAP["line_item_daily_summary"]

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            expected_markup = query.aggregate(markup=Sum(F("pretax_cost") * decimal.Decimal(0.1)))
            expected_markup = expected_markup.get("markup")

        self.accessor.populate_markup_cost(0.1, None)
        with schema_context(self.schema):
            query = self.accessor._get_db_obj_query(summary_table_name).aggregate(Sum("markup_cost"))
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    def test_populate_ocp_on_azure_cost_daily_summary(self):
        """Test the method to run OpenShift on Azure SQL."""
        summary_table_name = AZURE_REPORT_TABLE_MAP["ocp_on_azure_daily_summary"]
        project_summary_table_name = AZURE_REPORT_TABLE_MAP["ocp_on_azure_project_daily_summary"]
        markup_value = decimal.Decimal(0.1)

        summary_table = getattr(self.accessor.report_schema, summary_table_name)
        project_table = getattr(self.accessor.report_schema, project_summary_table_name)

        today = DateHelper().today
        last_month = DateHelper().last_month_start
        azure_bills = get_bills_from_provider(self.azure_provider_uuid, self.schema, last_month, today)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in azure_bills]
        cluster_id = self.ocp_on_azure_ocp_provider.authentication.provider_resource_name

        self.accessor.populate_ocp_on_azure_cost_daily_summary(last_month, today, cluster_id, bill_ids, markup_value)

        li_table_name = AZURE_REPORT_TABLE_MAP["line_item"]
        with schema_context(self.schema):
            li_table = getattr(self.accessor.report_schema, li_table_name)
            sum_azure_cost = li_table.objects.aggregate(Sum("pretax_cost"))["pretax_cost__sum"]

        with schema_context(self.schema):
            sum_cost = summary_table.objects.all().aggregate(Sum("pretax_cost"))["pretax_cost__sum"]
            sum_project_cost = project_table.objects.all().aggregate(Sum("pretax_cost"))["pretax_cost__sum"]
            self.assertNotEqual(sum_cost, 0)
            self.assertAlmostEqual(sum_cost, sum_project_cost, 4)
            self.assertLessEqual(sum_cost, sum_azure_cost)

        with schema_context(self.schema):
            sum_cost = summary_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("pretax_cost"))[
                "pretax_cost__sum"
            ]
            sum_project_cost = project_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("pretax_cost"))[
                "pretax_cost__sum"
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

            self.assertLessEqual(sum_cost, sum_azure_cost)
            self.assertAlmostEqual(sum_cost, sum_project_cost, 4)
            self.assertAlmostEqual(sum_markup_cost, sum_cost * markup_value, 4)
            self.assertAlmostEqual(sum_markup_cost_project, sum_cost * markup_value, 4)
            self.assertAlmostEqual(sum_project_markup_cost_project, sum_pod_cost * markup_value, 4)
