#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCPReportDBAccessor utility object."""
import datetime
import decimal
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from dateutil import relativedelta
from django.conf import settings
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from django_tenants.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.metrics.constants import DEFAULT_DISTRIBUTION_TYPE
from api.models import Provider
from api.utils import DateHelper
from koku.trino_database import TrinoHiveMetastoreError
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.processor.parquet.summary_sql_metadata import SummarySqlMetadata
from masu.test import MasuTestCase
from reporting.models import OCPGCPCostLineItemProjectDailySummaryP
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPTagsSummary
from reporting.provider.gcp.models import GCPTopology
from reporting.provider.gcp.models import TRINO_OCP_GCP_DAILY_SUMMARY_TABLE
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


class GCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportDBAccessor object."""

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.accessor = GCPReportDBAccessor(schema=self.schema)
        self.manifest = CostUsageReportManifest.objects.filter(provider_id=self.gcp_provider.uuid).first()

    def test_get_gcp_scan_range_from_report_name_with_manifest(self):
        """Test that we can scan range given the manifest id."""
        CostUsageReportStatus.objects.filter(manifest=self.manifest).delete()
        today_date = self.dh.today
        expected_start_date = "2020-11-01"
        expected_end_date = "2020-11-30"
        etag = "1234"
        invoice_month = "202011"
        CostUsageReportStatus.objects.create(
            report_name=f"{invoice_month}_{etag}_{expected_start_date}:{expected_end_date}.csv",
            completed_datetime=today_date,
            started_datetime=today_date,
            etag=etag,
            manifest=self.manifest,
        )
        scan_range = self.accessor.get_gcp_scan_range_from_report_name(manifest_id=self.manifest.id)
        self.assertEqual(expected_start_date, scan_range.get("start"))
        self.assertEqual(expected_end_date, scan_range.get("end"))

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
        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider.uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

            summary_entry = GCPCostEntryLineItemDailySummary.objects.all().aggregate(
                Min("usage_start"), Max("usage_start")
            )
            start_date = summary_entry["usage_start__min"]
            end_date = summary_entry["usage_start__max"]

        with schema_context(self.schema):
            expected_markup = GCPCostEntryLineItemDailySummary.objects.filter(cost_entry_bill__in=bill_ids).aggregate(
                markup=Sum(F("unblended_cost") * decimal.Decimal(0.1))
            )
            expected_markup = expected_markup.get("markup")

        self.accessor.populate_markup_cost(decimal.Decimal(0.1), start_date, end_date, bill_ids)
        with schema_context(self.schema):
            query = GCPCostEntryLineItemDailySummary.objects.filter(cost_entry_bill__in=bill_ids).aggregate(
                Sum("markup_cost")
            )
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    def test_get_bill_query_before_date(self):
        """Test that gets a query for cost entry bills before a date."""
        with schema_context(self.schema):
            first_entry = GCPCostEntryBill.objects.first()

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

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_line_item_daily_summary_table_trino(self, mock_trino):
        """Test that we construst our SQL and query using Trino."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        invoice_month = self.dh.gcp_find_invoice_months_in_date_range(start_date, end_date)[0]
        invoice_month_date = self.dh.invoice_month_start(invoice_month)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.gcp_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_line_item_daily_summary_table_trino(
            start_date, end_date, self.gcp_provider_uuid, current_bill_id, markup_value, invoice_month_date
        )
        mock_trino.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_ocp_on_gcp_ui_summary_tables_trino(
        self,
        mock_trino,
    ):
        """Test that Trino is used to populate UI summary."""
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)
        self.accessor.populate_ocp_on_gcp_ui_summary_tables_trino(
            start_date, end_date, self.gcp_test_provider_uuid, self.ocp_test_provider_uuid
        )
        mock_trino.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_raw_sql_query")
    @patch("masu.database.gcp_report_db_accessor.is_managed_ocp_cloud_summary_enabled", return_value=True)
    def test_populate_ocp_on_gcp_ui_summary_tables_trino_managed(
        self,
        mock_unleash,
        mock_trino,
    ):
        """Test that Trino is used to populate UI summary."""
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)
        self.accessor.populate_ocp_on_gcp_ui_summary_tables_trino(
            start_date, end_date, self.gcp_test_provider_uuid, self.ocp_test_provider_uuid
        )
        mock_trino.assert_called()

    def test_populate_enabled_tag_keys(self):
        """Test that enabled tag keys are populated."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.gcp_provider_uuid, start_date)
        with schema_context(self.schema):
            GCPTagsSummary.objects.all().delete()
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP).delete()
            bill_ids = [bill.id for bill in bills]
            self.assertEqual(EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP).count(), 0)
            self.accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            self.assertNotEqual(EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP).count(), 0)

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, GCPCostEntryLineItemDailySummary)

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, GCP_REPORT_TABLE_MAP)

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.delete_ocp_on_gcp_hive_partition_by_day")
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.delete_hive_partition_by_month")
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_gcp_cost_daily_summary_trino(self, mock_trino, mock_month_delete, mock_delete):
        """Test that we construst our SQL and query using Trino."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.gcp_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = cost_model_accessor.distribution_info.get("distribution_type", DEFAULT_DISTRIBUTION_TYPE)

        self.accessor.populate_ocp_on_gcp_cost_daily_summary_trino(
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
        mock_trino.assert_called()
        mock_month_delete.assert_called()
        mock_delete.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.delete_ocp_on_gcp_hive_partition_by_day")
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.delete_hive_partition_by_month")
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_multipart_sql_query")
    @patch("masu.database.gcp_report_db_accessor.is_managed_ocp_cloud_summary_enabled", return_value=True)
    def test_populate_ocp_on_gcp_cost_daily_summary_trino_managed(
        self, mock_unleash, mock_trino, mock_month_delete, mock_delete
    ):
        """Test that we construst our SQL and query using Trino."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.gcp_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.gcp_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = cost_model_accessor.distribution_info.get("distribution_type", DEFAULT_DISTRIBUTION_TYPE)

        self.accessor.populate_ocp_on_gcp_cost_daily_summary_trino(
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
        mock_trino.assert_called()
        mock_month_delete.assert_called()
        mock_delete.assert_called()

    def test_get_openshift_on_cloud_matched_tags(self):
        """Test that matched tags are returned."""
        start_date = self.dh.this_month_start.date()

        with schema_context(self.schema_name):
            bills = self.accessor.bills_for_provider_uuid(self.gcp_provider_uuid, start_date)
            bill_id = bills.first().id

        matched_tags = self.accessor.get_openshift_on_cloud_matched_tags(bill_id)

        self.assertGreater(len(matched_tags), 0)
        self.assertIsInstance(matched_tags[0], dict)

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_openshift_on_cloud_matched_tags_trino(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        invoice_month = self.dh.gcp_find_invoice_months_in_date_range(start_date, end_date)[0]
        invoice_month_date = self.dh.invoice_month_start(invoice_month)
        ocp_uuids = (self.ocp_on_gcp_ocp_provider.uuid,)

        self.accessor.get_openshift_on_cloud_matched_tags_trino(
            self.gcp_provider_uuid,
            ocp_uuids,
            start_date,
            end_date,
            invoice_month_date=invoice_month_date,
        )
        mock_trino.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_check_for_matching_enabled_keys_no_matches(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        with schema_context(self.schema):
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP).delete()
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertFalse(value)

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_check_for_matching_enabled_keys(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertTrue(value)

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_raw_sql_query")
    def test_back_populate_ocp_infrastructure_costs(self, mock_sql_execute):
        """Test that ocp on gcp back populate runs"""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        report_period_id = 4
        self.accessor.back_populate_ocp_infrastructure_costs(start_date, end_date, report_period_id)

        mock_sql_execute.assert_called()

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

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        invoice_month = self.dh.gcp_find_invoice_months_in_date_range(start_date, end_date)[0]
        invoice_month_date = self.dh.invoice_month_start(invoice_month)
        self.accessor.populate_gcp_topology_information_tables(
            self.gcp_provider, start_date, end_date, invoice_month_date
        )

        with schema_context(self.schema):
            records = GCPTopology.objects.all()
            self.assertEqual(records.count(), len(mock_topo_record))
            record = records.first()
            self.assertEqual(record.source_uuid, source_uuid)

        # attempt to populate a second time but verify no new entry added:
        self.accessor.populate_gcp_topology_information_tables(
            self.gcp_provider, start_date, end_date, invoice_month_date
        )
        with schema_context(self.schema):
            records = GCPTopology.objects.all()
            self.assertEqual(records.count(), len(mock_topo_record))

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_gcp_topology_trino(self, mock_trino):
        """Test that we call Trino to get topology."""
        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        invoice_month = self.dh.gcp_find_invoice_months_in_date_range(start_date, end_date)[0]
        invoice_month_date = self.dh.invoice_month_start(invoice_month)
        self.accessor.get_gcp_topology_trino(self.gcp_provider_uuid, start_date, end_date, invoice_month_date)

        mock_trino.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_raw_sql_query")
    def test_populate_ocp_gcp_ui_summary_tables(self, mock_sql):
        """Test that we construst our SQL and query using Trino."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        summary_sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "gcp_source_uuid": self.gcp_provider_uuid,
            "ocp_source_uuid": self.ocp_on_gcp_ocp_provider,
        }
        self.accessor.populate_ocp_on_gcp_ui_summary_tables(summary_sql_params)
        mock_sql.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_raw_sql_query")
    def test_populate_ocp_on_gcp_tag_information_assert_call(self, mock_trino):
        """Test that we construst our SQL and execute our query."""
        report_period_id = 1
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        mock_gcp_bills = [Mock(), Mock()]
        self.accessor.populate_ocp_on_gcp_tag_information(mock_gcp_bills, start_date, end_date, report_period_id)
        mock_trino.assert_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.schema_exists_trino")
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.trino_db.connect")
    @patch("time.sleep", return_value=None)
    def test_delete_ocp_on_gcp_hive_partition_by_day(
        self, mock_sleep, mock_connect, mock_table_exists, mock_schema_exists
    ):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_ocp_on_gcp_hive_partition_by_day(
            [1], self.gcp_provider_uuid, self.ocp_provider_uuid, "2022", "01"
        )
        mock_connect.assert_not_called()

        mock_connect.reset_mock()

        mock_schema_exists.return_value = True
        attrs = {"cursor.side_effect": TrinoExternalError({"errorName": "HIVE_METASTORE_ERROR"})}
        mock_connect.return_value = Mock(**attrs)

        with self.assertRaises(TrinoHiveMetastoreError):
            self.accessor.delete_ocp_on_gcp_hive_partition_by_day(
                [1], self.gcp_provider_uuid, self.ocp_provider_uuid, "2022", "01"
            )

        mock_connect.assert_called()
        self.assertEqual(mock_connect.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_delete_gcp_hive_partition_by_month(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        table = "reporting_ocpgcpcostlineitem_project_daily_summary_temp"
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with patch(
            "masu.database.report_db_accessor_base.ReportDBAccessorBase.schema_exists_trino", return_value=True
        ):
            with self.assertRaises(TrinoExternalError):
                self.accessor.delete_hive_partition_by_month(table, self.ocp_provider_uuid, "2022", "01")
            mock_trino.assert_called()
            # Confirms that the error log would be logged on last attempt
            self.assertEqual(mock_trino.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

        # Test that deletions short circuit if the schema does not exist
        mock_trino.reset_mock()
        mock_table_exist.reset_mock()
        with patch(
            "masu.database.report_db_accessor_base.ReportDBAccessorBase.schema_exists_trino", return_value=False
        ):
            self.accessor.delete_hive_partition_by_month(table, self.ocp_provider_uuid, "2022", "01")
            mock_trino.assert_not_called()
            mock_table_exist.assert_not_called()

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.schema_exists_trino")
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.trino_db.connect")
    @patch("time.sleep", return_value=None)
    def test_delete_ocp_on_gcp_hive_partition_by_day_managed_table(
        self, mock_sleep, mock_connect, mock_table_exists, mock_schema_exists
    ):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_ocp_on_gcp_hive_partition_by_day(
            [1],
            self.gcp_provider_uuid,
            self.ocp_provider_uuid,
            "2022",
            "01",
            TRINO_OCP_GCP_DAILY_SUMMARY_TABLE,
        )
        mock_connect.assert_not_called()

        mock_connect.reset_mock()

        mock_schema_exists.return_value = True
        attrs = {"cursor.side_effect": TrinoExternalError({"errorName": "HIVE_METASTORE_ERROR"})}
        mock_connect.return_value = Mock(**attrs)

        with self.assertRaises(TrinoHiveMetastoreError):
            self.accessor.delete_ocp_on_gcp_hive_partition_by_day(
                [1],
                self.gcp_provider_uuid,
                self.ocp_provider_uuid,
                "2022",
                "01",
                TRINO_OCP_GCP_DAILY_SUMMARY_TABLE,
            )

        mock_connect.assert_called()
        self.assertEqual(mock_connect.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    def test_update_line_item_daily_summary_with_tag_mapping(self):
        """
        This tests the tag mapping feature.
        """
        populated_keys = []
        with schema_context(self.schema):
            enabled_tags = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP, enabled=True)
            for enabled_tag in enabled_tags:
                tag_count = GCPCostEntryLineItemDailySummary.objects.filter(
                    tags__has_key=enabled_tag.key,
                    usage_start__gte=self.dh.this_month_start,
                    usage_start__lte=self.dh.today,
                ).count()
                if tag_count > 0:
                    key_metadata = [enabled_tag.key, enabled_tag, tag_count]
                    populated_keys.append(key_metadata)
                if len(populated_keys) == 2:
                    break
            parent_key, parent_obj, parent_count = populated_keys[0]
            child_key, child_obj, child_count = populated_keys[1]
            TagMapping.objects.create(parent=parent_obj, child=child_obj)
            self.accessor.update_line_item_daily_summary_with_tag_mapping(self.dh.this_month_start, self.dh.today)
            expected_parent_count = parent_count + child_count
            actual_parent_count = GCPCostEntryLineItemDailySummary.objects.filter(
                tags__has_key=parent_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(expected_parent_count, actual_parent_count)
            actual_child_count = GCPCostEntryLineItemDailySummary.objects.filter(
                tags__has_key=child_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(0, actual_child_count)

    def test_populate_ocp_on_gcp_tag_information(self):
        """
        This tests the tag mapping feature.
        """
        populated_keys = []
        report_period_id = 1
        with schema_context(self.schema):
            enabled_tags = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP, enabled=True)
            for enabled_tag in enabled_tags:
                tag_count = OCPGCPCostLineItemProjectDailySummaryP.objects.filter(
                    tags__has_key=enabled_tag.key,
                    usage_start__gte=self.dh.this_month_start,
                    usage_start__lte=self.dh.today,
                ).count()
                if tag_count > 0:
                    key_metadata = [enabled_tag.key, enabled_tag, tag_count]
                    populated_keys.append(key_metadata)
                if len(populated_keys) == 2:
                    break
            bill_ids = OCPGCPCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=enabled_tag.key,
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today,
            ).values_list("cost_entry_bill", flat=True)
            parent_key, parent_obj, parent_count = populated_keys[0]
            child_key, child_obj, child_count = populated_keys[1]
            TagMapping.objects.create(parent=parent_obj, child=child_obj)
            self.accessor.populate_ocp_on_gcp_tag_information(
                bill_ids, self.dh.this_month_start, self.dh.today, report_period_id
            )
            expected_parent_count = parent_count + child_count
            actual_parent_count = OCPGCPCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=parent_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(expected_parent_count, actual_parent_count)
            actual_child_count = OCPGCPCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=child_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(0, actual_child_count)

    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.delete_ocp_on_gcp_hive_partition_by_day")
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_cloud_daily_trino(self, mock_trino, mock_partition_delete):
        """
        Test that calling ocp on cloud populate triggers the deletes and summary sql.
        """
        matched_tags = "fake-tags"
        mparams = SummarySqlMetadata(
            self.schema_name,
            [self.ocp_provider_uuid],
            self.gcp_provider_uuid,
            DateHelper().today,
            DateHelper().tomorrow,
            matched_tags,
        )
        self.accessor.populate_ocp_on_cloud_daily_trino(mparams)
        mock_partition_delete.assert_called_with(
            mparams.days_tup,
            self.gcp_provider_uuid,
            self.ocp_provider_uuid,
            mparams.year,
            mparams.month,
            TRINO_OCP_GCP_DAILY_SUMMARY_TABLE,
        )
        mock_trino.assert_called()
