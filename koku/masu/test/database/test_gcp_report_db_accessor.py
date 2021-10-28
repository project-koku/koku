#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCPReportDBAccessor utility object."""
import decimal
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from dateutil import relativedelta
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from koku.database import get_model
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPEnabledTagKeys
from reporting.provider.gcp.models import GCPTagsSummary
from reporting.provider.gcp.models import GCPTopology
from reporting_common.models import CostUsageReportStatus


class GCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = GCPReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema

        cls.all_tables = list(GCP_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            GCP_REPORT_TABLE_MAP["bill"],
            GCP_REPORT_TABLE_MAP["product"],
            GCP_REPORT_TABLE_MAP["project"],
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
            "provider_id": self.gcp_provider.uuid,
        }
        self.manifest = self.manifest_accessor.add(**self.manifest_dict)

    def test_get_gcp_scan_range_from_report_name_with_manifest(self):
        """Test that we can scan range given the manifest id."""
        dh = DateHelper()
        today_date = dh.today
        expected_start_date = "2020-11-01"
        expected_end_date = "2020-11-30"
        etag = "1234"
        invoice_month = "202011"
        CostUsageReportStatus.objects.create(
            report_name=f"{invoice_month}_{etag}_{expected_start_date}:{expected_end_date}.csv",
            last_completed_datetime=today_date,
            last_started_datetime=today_date,
            etag=etag,
            manifest=self.manifest,
        )
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(manifest_id=self.manifest.id)
        self.assertEqual(str(expected_start_date), scan_range.get("start"))
        self.assertEqual(str(expected_end_date), scan_range.get("end"))

    def test_get_gcp_scan_range_from_report_name_with_report_name(self):
        """Test that we can scan range given the manifest id."""
        expected_start_date = "2020-11-01"
        expected_end_date = "2020-11-30"
        report_name = f"202011_1234_{expected_start_date}:{expected_end_date}.csv"
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(report_name=report_name)
        self.assertEqual(str(expected_start_date), scan_range.get("start"))
        self.assertEqual(str(expected_end_date), scan_range.get("end"))

    def test_get_gcp_scan_range_from_report_name_with_value_error(self):
        """Test that we can scan range given the manifest id."""
        expected_start_date = "2020-11-01"
        expected_end_date = "2020-11-30"
        report_name = f"202011-1234-{expected_start_date}-{expected_end_date}.csv"
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(report_name=report_name)
        self.assertIsNone(scan_range.get("start"))
        self.assertIsNone(scan_range.get("end"))

    def test_get_gcp_scan_range_from_report_name_with_manifest_no_report(self):
        """Test that we can scan range given the manifest id."""
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(manifest_id=self.manifest.id)
        self.assertIsNone(scan_range.get("start"))
        self.assertIsNone(scan_range.get("end"))

    def test_populate_markup_cost(self):
        """Test that the daily summary table is populated."""
        summary_table_name = GCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider.uuid)
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

        self.accessor.populate_markup_cost(0.1, start_date, end_date, bill_ids)
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
            table_name = GCP_REPORT_TABLE_MAP["bill"]
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

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_populate_line_item_daily_summary_table_presto(self, mock_presto):
        """Test that we construst our SQL and query using Presto."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.gcp_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_line_item_daily_summary_table_presto(
            start_date, end_date, self.gcp_provider_uuid, current_bill_id, markup_value
        )
        mock_presto.assert_called()

    def test_populate_enabled_tag_keys(self):
        """Test that enabled tag keys are populated."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.gcp_provider_uuid, start_date)
        with schema_context(self.schema):
            GCPTagsSummary.objects.all().delete()
            GCPEnabledTagKeys.objects.all().delete()
            bill_ids = [bill.id for bill in bills]
            self.assertEqual(GCPEnabledTagKeys.objects.count(), 0)
            self.accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            self.assertNotEqual(GCPEnabledTagKeys.objects.count(), 0)

    def test_update_line_item_daily_summary_with_enabled_tags(self):
        """Test that we filter the daily summary table's tags with only enabled tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.gcp_provider_uuid, start_date)
        with schema_context(self.schema):
            GCPTagsSummary.objects.all().delete()
            key_to_keep = GCPEnabledTagKeys.objects.first()
            GCPEnabledTagKeys.objects.exclude(key=key_to_keep.key).delete()
            bill_ids = [bill.id for bill in bills]
            self.accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, bill_ids)
            tags = (
                GCPCostEntryLineItemDailySummary.objects.filter(
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
            start_date = GCPCostEntryLineItemDailySummary.objects.aggregate(Max("usage_start")).get("usage_start__max")
            end_date = start_date

        table_query = GCPCostEntryLineItemDailySummary.objects.filter(
            source_uuid=self.gcp_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
        )
        with schema_context(self.schema):
            self.assertNotEqual(table_query.count(), 0)

        self.accessor.delete_line_item_daily_summary_entries_for_date_range(
            self.gcp_provider_uuid, start_date, end_date
        )

        with schema_context(self.schema):
            self.assertEqual(table_query.count(), 0)

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, GCPCostEntryLineItemDailySummary)
        self.assertEqual(self.accessor.line_item_daily_table, get_model("GCPCostEntryLineItemDaily"))
        self.assertEqual(self.accessor.line_item_table, get_model("GCPCostEntryLineItem"))

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, GCP_REPORT_TABLE_MAP)

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_presto_multipart_sql_query")
    def test_populate_ocp_on_gcp_cost_daily_summary_presto(self, mock_presto):
        """Test that we construst our SQL and query using Presto."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.gcp_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = cost_model_accessor.distribution

        self.accessor.populate_ocp_on_gcp_cost_daily_summary_presto(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.ocp_cluster_id,
            self.gcp_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_presto.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_get_openshift_on_cloud_matched_tags_trino(self, mock_presto):
        """Test that Trino is used to find matched tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        self.accessor.get_openshift_on_cloud_matched_tags_trino(
            self.gcp_provider_uuid, self.ocp_provider_uuid, start_date, end_date
        )
        mock_presto.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_presto_multipart_sql_query")
    def test_back_populate_ocp_on_gcp_daily_summary_trino(self, mock_presto):
        """Test that ocp on gcp back populate runs"""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        report_period_id = 4
        self.accessor.back_populate_ocp_on_gcp_daily_summary_trino(start_date, end_date, report_period_id)

        mock_presto.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.get_gcp_topology_trino")
    def test_populate_gcp_topology_information_tables(self, mock_get_topo):
        """Test that GCP Topology table is populated."""
        source_uuid = uuid4()
        mock_topo_record = [
            (
                source_uuid,
                "account_12345",
                "project_one",
                "The Best Project",
                "Service_1",
                "The Best Service",
                "US East",
            )
        ]
        mock_get_topo.return_value = mock_topo_record

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.accessor.populate_gcp_topology_information_tables(self.gcp_provider, start_date, end_date)

        with schema_context(self.schema):
            records = GCPTopology.objects.all()
            self.assertEqual(records.count(), len(mock_topo_record))
            record = records.first()
            self.assertEqual(record.source_uuid, source_uuid)

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_get_gcp_topology_trino(self, mock_trino):
        """Test that we call Trino to get topology."""
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.accessor.get_gcp_topology_trino(self.gcp_provider_uuid, start_date, end_date)

        mock_trino.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_presto_multipart_sql_query")
    def test_populate_ui_summary_tables(self, mock_presto):
        """Test that we construst our SQL and query using Presto."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        report_period_id = 4

        self.accessor.populate_ui_summary_tables(
            start_date, end_date, self.ocp_provider_uuid, self.gcp_provider_uuid, report_period_id
        )
        mock_presto.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_raw_sql_query")
    def test_populate_ocp_on_gcp_tags_summary_table(self, mock_presto):
        """Test that we construst our SQL and execute our query."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        mock_gcp_bills = [Mock(), Mock()]
        self.accessor.populate_ocp_on_gcp_tags_summary_table(mock_gcp_bills, start_date, end_date)
        mock_presto.assert_called()
