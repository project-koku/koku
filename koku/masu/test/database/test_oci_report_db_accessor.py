#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCIReportDBAccessor utility object."""
import decimal
from unittest.mock import patch

from dateutil import relativedelta
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.database import OCI_CUR_TABLE_MAP
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.oci_report_db_accessor import OCIReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from reporting.provider.oci.models import OCICostEntryLineItemDailySummary
from reporting.provider.oci.models import OCIEnabledTagKeys
from reporting.provider.oci.models import OCITagsSummary


class OCIReportDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = OCIReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema

        cls.all_tables = list(OCI_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            OCI_CUR_TABLE_MAP["bill"],
        ]
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        today = DateAccessor().today_with_timezone("UTC")
        billing_start = today.replace(day=1)

        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_id": self.oci_provider.uuid,
        }
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)

    def test_populate_markup_cost(self):
        """Test that the daily summary table is populated."""
        summary_table_name = OCI_CUR_TABLE_MAP["line_item_daily_summary"]
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.oci_provider.uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            start_date = summary_entry["usage_start__min"]
            end_date = summary_entry["usage_start__max"]

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            expected_markup = query.filter(cost_entry_bill__in=bill_ids).aggregate(
                markup=Sum(F("cost") * decimal.Decimal(0.1))
            )
            expected_markup = expected_markup.get("markup")

        self.accessor.populate_markup_cost(decimal.Decimal(0.1), start_date, end_date, bill_ids)
        with schema_context(self.schema):
            query = (
                self.accessor._get_db_obj_query(summary_table_name)
                .filter(cost_entry_bill__in=bill_ids)
                .aggregate(Sum("markup_cost"))
            )
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    def test_get_bill_query_before_date(self):
        """Test that gets a query for cost entry bills before a date."""
        with schema_context(self.schema):
            table_name = OCI_CUR_TABLE_MAP["bill"]
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

    @patch("masu.database.oci_report_db_accessor.OCIReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_line_item_daily_summary_table_trino(self, mock_trino):
        """Test that we construst our SQL and query using Trino."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.oci_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.oci_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_line_item_daily_summary_table_trino(
            start_date, end_date, self.oci_provider_uuid, current_bill_id, markup_value
        )
        mock_trino.assert_called()

    def test_populate_enabled_tag_keys(self):
        """Test that enabled tag keys are populated."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.oci_provider_uuid, start_date)
        with schema_context(self.schema):
            OCITagsSummary.objects.all().delete()
            OCIEnabledTagKeys.objects.all().delete()
            bill_ids = [bill.id for bill in bills]
            self.assertEqual(OCIEnabledTagKeys.objects.count(), 0)
            self.accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            self.assertNotEqual(OCIEnabledTagKeys.objects.count(), 0)

    def test_update_line_item_daily_summary_with_enabled_tags(self):
        """Test that we filter the daily summary table's tags with only enabled tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.oci_provider_uuid, start_date)
        with schema_context(self.schema):
            OCITagsSummary.objects.all().delete()
            key_to_keep = OCIEnabledTagKeys.objects.filter(key="app").first()
            OCIEnabledTagKeys.objects.all().update(enabled=False)
            OCIEnabledTagKeys.objects.filter(key="app").update(enabled=True)
            bill_ids = [bill.id for bill in bills]
            self.accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, bill_ids)
            tags = (
                OCICostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, cost_entry_bill_id__in=bill_ids
                )
                .values_list("tags")
                .distinct()
            )

            for tag in tags:
                tag_dict = tag[0] if tag[0] is not None else {}  # account for null tags value
                tag_keys = list(tag_dict.keys())
                if tag_keys:
                    self.assertEqual([key_to_keep.key], tag_keys)
                else:
                    self.assertEqual([], tag_keys)

    def test_delete_line_item_daily_summary_entries_for_date_range(self):
        """Test that daily summary rows are deleted."""
        with schema_context(self.schema):
            start_date = OCICostEntryLineItemDailySummary.objects.aggregate(Max("usage_start")).get("usage_start__max")
            end_date = start_date

        table_query = OCICostEntryLineItemDailySummary.objects.filter(
            source_uuid=self.oci_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
        )
        with schema_context(self.schema):
            self.assertNotEqual(table_query.count(), 0)

        self.accessor.delete_line_item_daily_summary_entries_for_date_range(
            self.oci_provider_uuid, start_date, end_date
        )

        with schema_context(self.schema):
            self.assertEqual(table_query.count(), 0)

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, OCICostEntryLineItemDailySummary)

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, OCI_CUR_TABLE_MAP)
