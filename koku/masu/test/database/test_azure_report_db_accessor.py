#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportDBAccessor utility object."""
import decimal
from unittest.mock import Mock
from unittest.mock import patch

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
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.test import MasuTestCase
from reporting.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import AzureTagsSummary
from reporting.provider.azure.models import TRINO_MANAGED_OCP_AZURE_DAILY_TABLE
from reporting.provider.azure.models import TRINO_OCP_ON_AZURE_DAILY_TABLE


class AzureReportDBAccessorTest(MasuTestCase):
    """Test Cases for the AzureReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = AzureReportDBAccessor(schema=cls.schema)

        cls.all_tables = list(AZURE_REPORT_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AZURE_REPORT_TABLE_MAP["bill"],
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

    def test_bills_for_provider_uuid(self):
        """Test that bills_for_provider_uuid returns the right bills."""
        bills = self.accessor.bills_for_provider_uuid(self.azure_provider_uuid, start_date=self.dh.this_month_start)
        with schema_context(self.schema):
            self.assertEqual(len(bills), 1)

    def test_populate_markup_cost(self):
        """Test that the daily summary table is populated."""
        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider_uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]
            summary_entry = AzureCostEntryLineItemDailySummary.objects.all().aggregate(
                Min("usage_start"), Max("usage_start")
            )
            start_date = summary_entry["usage_start__min"]
            end_date = summary_entry["usage_start__max"]

        with schema_context(self.schema):
            expected_markup = AzureCostEntryLineItemDailySummary.objects.filter(
                cost_entry_bill__in=bill_ids
            ).aggregate(markup=Sum(F("pretax_cost") * decimal.Decimal(0.1)))
            expected_markup = expected_markup.get("markup")

        self.accessor.populate_markup_cost(
            self.azure_provider_uuid, decimal.Decimal(0.1), start_date, end_date, bill_ids
        )
        with schema_context(self.schema):
            query = AzureCostEntryLineItemDailySummary.objects.filter(cost_entry_bill__in=bill_ids).aggregate(
                Sum("markup_cost")
            )
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_line_item_daily_summary_table_trino(self, mock_trino):
        """Test that we construst our SQL and query using Trino."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.azure_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_line_item_daily_summary_table_trino(
            start_date, end_date, self.azure_provider_uuid, current_bill_id, markup_value
        )
        mock_trino.assert_called()

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_ocp_on_azure_ui_summary_tables_trino(self, mock_trino):
        """Test that Trino is used to populate UI summary."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        self.accessor.populate_ocp_on_azure_ui_summary_tables_trino(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.azure_provider_uuid,
        )
        mock_trino.assert_called()

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_raw_sql_query")
    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_azure_cost_daily_summary_trino(self, mock_trino, mock_delete):
        """Test that we construst our SQL and query using Trino."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = cost_model_accessor.distribution_info.get("distribution_type", DEFAULT_DISTRIBUTION_TYPE)

        self.accessor.populate_ocp_on_azure_cost_daily_summary_trino(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.azure_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_trino.assert_called()
        mock_delete.assert_called()

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_raw_sql_query")
    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_azure_cost_daily_summary_trino_memory_distribution(self, mock_trino, mock_delete):
        """Test that we construst our SQL and query using Trino."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = "memory"

        self.accessor.populate_ocp_on_azure_cost_daily_summary_trino(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.azure_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_trino.assert_called()
        mock_delete.assert_called()

    def test_populate_enabled_tag_keys(self):
        """Test that enabled tag keys are populated."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.azure_provider_uuid, start_date)
        with schema_context(self.schema):
            AzureTagsSummary.objects.all().delete()
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AZURE).delete()
            bill_ids = [bill.id for bill in bills]
            self.assertEqual(EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AZURE).count(), 0)
            self.accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            self.assertNotEqual(EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AZURE).count(), 0)

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, AzureCostEntryLineItemDailySummary)

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, AZURE_REPORT_TABLE_MAP)

    def test_get_openshift_on_cloud_matched_tags(self):
        """Test that matched tags are returned."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()

        with schema_context(self.schema_name):
            bills = self.accessor.bills_for_provider_uuid(self.azure_provider_uuid, start_date)
            bill_id = bills.first().id

        matched_tags = self.accessor.get_openshift_on_cloud_matched_tags(bill_id)

        self.assertGreater(len(matched_tags), 0)
        self.assertIsInstance(matched_tags[0], dict)

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_openshift_on_cloud_matched_tags_trino(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        ocp_uuids = (self.ocp_on_azure_ocp_provider.uuid,)

        self.accessor.get_openshift_on_cloud_matched_tags_trino(
            self.azure_provider_uuid,
            ocp_uuids,
            start_date,
            end_date,
        )
        mock_trino.assert_called()

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor.schema_exists_trino")
    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.trino_db.connect")
    @patch("time.sleep", return_value=None)
    def test_delete_ocp_on_azure_hive_partition_by_day(
        self, mock_sleep, mock_connect, mock_table_exists, mock_schema_exists
    ):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_ocp_on_azure_hive_partition_by_day(
            [1], self.azure_provider_uuid, self.ocp_provider_uuid, "2022", "01"
        )
        mock_connect.assert_not_called()

        mock_connect.reset_mock()

        mock_schema_exists.return_value = True
        attrs = {"cursor.side_effect": TrinoExternalError({"errorName": "HIVE_METASTORE_ERROR"})}
        mock_connect.return_value = Mock(**attrs)

        with self.assertRaises(TrinoHiveMetastoreError):
            self.accessor.delete_ocp_on_azure_hive_partition_by_day(
                [1], self.azure_provider_uuid, self.ocp_provider_uuid, "2022", "01"
            )

        mock_connect.assert_called()
        self.assertEqual(mock_connect.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_raw_sql_query")
    def test_check_for_matching_enabled_keys_no_matches(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        with schema_context(self.schema):
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AZURE).delete()
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertFalse(value)

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_raw_sql_query")
    def test_check_for_matching_enabled_keys(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertTrue(value)

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_delete_azure_hive_partition_by_month(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        table = "reporting_ocpazurecostlineitem_project_daily_summary_temp"
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

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor.schema_exists_trino")
    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.trino_db.connect")
    @patch("time.sleep", return_value=None)
    def test_delete_ocp_on_azure_hive_partition_by_day_managed_table(
        self, mock_sleep, mock_connect, mock_table_exists, mock_schema_exists
    ):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_ocp_on_azure_hive_partition_by_day(
            [1],
            self.azure_provider_uuid,
            self.ocp_provider_uuid,
            "2022",
            "01",
            TRINO_MANAGED_OCP_AZURE_DAILY_TABLE,
        )
        mock_connect.assert_not_called()

        mock_connect.reset_mock()

        mock_schema_exists.return_value = True
        attrs = {"cursor.side_effect": TrinoExternalError({"errorName": "HIVE_METASTORE_ERROR"})}
        mock_connect.return_value = Mock(**attrs)

        with self.assertRaises(TrinoHiveMetastoreError):
            self.accessor.delete_ocp_on_azure_hive_partition_by_day(
                [1],
                self.azure_provider_uuid,
                self.ocp_provider_uuid,
                "2022",
                "01",
                TRINO_MANAGED_OCP_AZURE_DAILY_TABLE,
            )

        mock_connect.assert_called()
        self.assertEqual(mock_connect.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.azure_report_db_accessor.is_feature_cost_3592_tag_mapping_enabled")
    def test_update_line_item_daily_summary_with_tag_mapping(self, mock_unleash):
        """
        This tests the tag mapping feature.
        """
        mock_unleash.return_value = True
        populated_keys = []
        with schema_context(self.schema):
            enabled_tags = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AZURE, enabled=True)
            for enabled_tag in enabled_tags:
                tag_count = AzureCostEntryLineItemDailySummary.objects.filter(
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
            actual_parent_count = AzureCostEntryLineItemDailySummary.objects.filter(
                tags__has_key=parent_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(expected_parent_count, actual_parent_count)
            actual_child_count = AzureCostEntryLineItemDailySummary.objects.filter(
                tags__has_key=child_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(0, actual_child_count)

    @patch("masu.database.azure_report_db_accessor.is_feature_cost_3592_tag_mapping_enabled")
    def test_populate_ocp_on_azure_tag_information(self, mock_unleash):
        """
        This tests the tag mapping feature.
        """
        mock_unleash.return_value = True
        populated_keys = []
        report_period_id = 1
        with schema_context(self.schema):
            enabled_tags = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AZURE, enabled=True)
            for enabled_tag in enabled_tags:
                tag_count = OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                    tags__has_key=enabled_tag.key,
                    usage_start__gte=self.dh.this_month_start,
                    usage_start__lte=self.dh.today,
                ).count()
                if tag_count > 0:
                    key_metadata = [enabled_tag.key, enabled_tag, tag_count]
                    populated_keys.append(key_metadata)
                if len(populated_keys) == 2:
                    break
            bill_ids = OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=enabled_tag.key,
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today,
            ).values_list("cost_entry_bill", flat=True)
            parent_key, parent_obj, parent_count = populated_keys[0]
            child_key, child_obj, child_count = populated_keys[1]
            TagMapping.objects.create(parent=parent_obj, child=child_obj)
            self.accessor.populate_ocp_on_azure_tag_information(
                bill_ids, self.dh.this_month_start, self.dh.today, report_period_id
            )
            expected_parent_count = parent_count + child_count
            actual_parent_count = OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=parent_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(expected_parent_count, actual_parent_count)
            actual_child_count = OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=child_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(0, actual_child_count)

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor.delete_ocp_on_azure_hive_partition_by_day")
    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_cloud_daily_trino(self, mock_trino, mock_partition_delete):
        """
        Test that calling ocp on cloud populate triggers the deletes and summary sql.
        """
        start_date = "2024-08-01"
        end_date = "2024-08-05"
        year = "2024"
        month = "08"
        matched_tags = "fake-tags"
        expected_days = ("1", "2", "3", "4", "5")

        self.accessor.populate_ocp_on_cloud_daily_trino(
            self.azure_provider_uuid, self.ocp_provider_uuid, start_date, end_date, matched_tags
        )
        mock_partition_delete.assert_called_with(
            expected_days,
            self.azure_provider_uuid,
            self.ocp_provider_uuid,
            year,
            month,
            TRINO_MANAGED_OCP_AZURE_DAILY_TABLE,
        )
        mock_trino.assert_called()

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_trino_multipart_sql_query")
    def test_verify_populate_ocp_on_cloud_daily_trino(self, mock_trino):
        """
        Test validating trino tables.
        """
        verification_params = {
            "schema": self.schema,
            "cloud_source_uuid": self.azure_provider_uuid,
            "year": "2024",
            "month": "08",
            "managed_table": TRINO_MANAGED_OCP_AZURE_DAILY_TABLE,
            "parquet_table": TRINO_OCP_ON_AZURE_DAILY_TABLE,
        }
        with self.assertLogs("masu.database.azure_report_db_accessor", level="INFO") as logger:
            self.accessor.verify_populate_ocp_on_cloud_daily_trino(verification_params)
            assert any(
                "Verification successful" in log for log in logger.output
            ), "Verification successful not found in logs"

        mock_trino.side_effect = [[[False]]]
        with self.assertLogs("masu.database.azure_report_db_accessor", level="ERROR") as logger:
            self.accessor.verify_populate_ocp_on_cloud_daily_trino(verification_params)
            assert any("Verification failed" in log for log in logger.output), "Verification failed not found in logs"
