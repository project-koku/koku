#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSReportDBAccessor utility object."""
import datetime
import decimal
import pkgutil
from decimal import Decimal
from unittest.mock import Mock
from unittest.mock import patch

from dateutil import relativedelta
from django.conf import settings
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from django.db.utils import ProgrammingError
from django_tenants.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.metrics.constants import DEFAULT_DISTRIBUTION_TYPE
from api.provider.models import Provider
from koku.database import get_model
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.test import MasuTestCase
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSTagsSummary


class AWSReportDBAccessorTest(MasuTestCase):
    """Test Cases for the ReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = AWSReportDBAccessor(schema=cls.schema)

        cls.all_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.foreign_key_tables = [
            AWS_CUR_TABLE_MAP["bill"],
        ]
        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

        self.cluster_id = "testcluster"
        self.manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": self.dh.this_month_start,
            "num_total_files": 2,
            "provider_id": self.aws_provider.uuid,
        }

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

    def test_get_bill_query_before_date(self):
        """Test that gets a query for cost entry bills before a date."""
        with schema_context(self.schema):
            first_entry = AWSCostEntryBill.objects.first()

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

    def test_bills_for_provider_uuid(self):
        """Test that bills_for_provider_uuid returns the right bills."""
        bills = self.accessor.bills_for_provider_uuid(self.aws_provider.uuid, start_date=self.dh.today)
        with schema_context(self.schema):
            self.assertEqual(len(bills), 1)

    def test_populate_markup_cost(self):
        """Test that the daily summary table is populated."""
        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]

            summary_entry = AWSCostEntryLineItemDailySummary.objects.all().aggregate(
                Min("usage_start"), Max("usage_start")
            )
            start_date = summary_entry["usage_start__min"]
            end_date = summary_entry["usage_start__max"]

        with schema_context(self.schema):
            expected_markup = AWSCostEntryLineItemDailySummary.objects.filter(cost_entry_bill__in=bill_ids).aggregate(
                markup=Sum(F("unblended_cost") * decimal.Decimal(0.1))
            )
            expected_markup = expected_markup.get("markup")

        self.accessor.populate_markup_cost(
            self.aws_provider.uuid, decimal.Decimal(0.1), start_date, end_date, bill_ids
        )
        with schema_context(self.schema):
            query = AWSCostEntryLineItemDailySummary.objects.filter(cost_entry_bill__in=bill_ids).aggregate(
                Sum("markup_cost")
            )
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_line_item_daily_summary_table_trino(self, mock_trino):
        """Test that we construst our SQL and query using Trino."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_line_item_daily_summary_table_trino(
            start_date, end_date, self.aws_provider_uuid, current_bill_id, markup_value
        )
        mock_trino.assert_called()

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_ocp_on_aws_ui_summary_tables_trino(self, mock_trino):
        """Test that Trino is used to populate UI summary."""
        start_date = datetime.datetime.strptime("2023-05-01", "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime("2023-05-31", "%Y-%m-%d").date()

        self.accessor.populate_ocp_on_aws_ui_summary_tables_trino(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.aws_provider_uuid,
        )
        mock_trino.assert_called()

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.delete_ocp_on_aws_hive_partition_by_day")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.delete_hive_partition_by_month")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_aws_cost_daily_summary_trino(self, mock_trino, mock_month_delete, mock_delete):
        """Test that we construst our SQL and query using Trino."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = cost_model_accessor.distribution_info.get("distribution_type", DEFAULT_DISTRIBUTION_TYPE)

        self.accessor.populate_ocp_on_aws_cost_daily_summary_trino(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.aws_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_trino.assert_called()

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.delete_ocp_on_aws_hive_partition_by_day")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.delete_hive_partition_by_month")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_aws_cost_daily_summary_trino_memory_distribution(
        self, mock_trino, mock_month_delete, mock_delete
    ):
        """Test that we construst our SQL and query using Trino."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = "memory"

        self.accessor.populate_ocp_on_aws_cost_daily_summary_trino(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.aws_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_trino.assert_called()

    def test_populate_enabled_tag_keys(self):
        """Test that enabled tag keys are populated."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.aws_provider_uuid, start_date)
        with schema_context(self.schema):
            AWSTagsSummary.objects.all().delete()
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).delete()

            bill_ids = [bill.id for bill in bills]
            self.assertEqual(EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).count(), 0)
            self.accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            self.assertNotEqual(EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).count(), 0)

    def test_update_line_item_daily_summary_with_enabled_tags(self):
        """Test that we filter the daily summary table's tags with only enabled tags."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.aws_provider_uuid, start_date)
        with schema_context(self.schema):
            AWSTagsSummary.objects.all().delete()
            key_to_keep = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).filter(key="app").first()
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).update(enabled=False)
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).filter(key="app").update(enabled=True)
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

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, get_model("AWSCostEntryLineItemDailySummary"))

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, AWS_CUR_TABLE_MAP)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_openshift_on_cloud_matched_tags_trino(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        ocp_uuids = (self.ocp_on_aws_ocp_provider.uuid,)

        self.accessor.get_openshift_on_cloud_matched_tags_trino(
            self.aws_provider_uuid,
            ocp_uuids,
            start_date,
            end_date,
        )
        mock_trino.assert_called()

    def test_bad_sql_execution(self):
        script_file_name = "reporting_ocpallcostlineitem_project_daily_summary_aws.sql"
        script_file_path = f"{OCPReportDBAccessor.OCP_ON_ALL_SQL_PATH}{script_file_name}"
        with OCPReportDBAccessor(self.schema_name) as accessor:
            with self.assertRaises(ProgrammingError):
                accessor._execute_processing_script("masu.database", script_file_path, {})

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.schema_exists_trino")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.table_exists_trino")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_delete_ocp_on_aws_hive_partition_by_day(self, mock_trino, mock_table_exist, mock_schema_exists):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_ocp_on_aws_hive_partition_by_day(
            [1], self.aws_provider_uuid, self.ocp_provider_uuid, "2022", "01"
        )
        mock_trino.assert_not_called()

        mock_schema_exists.return_value = True
        mock_trino.reset_mock()
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with self.assertRaises(TrinoExternalError):
            self.accessor.delete_ocp_on_aws_hive_partition_by_day(
                [1], self.aws_provider_uuid, self.ocp_provider_uuid, "2022", "01"
            )
        mock_trino.assert_called()
        # Confirms that the error log would be logged on last attempt
        self.assertEqual(mock_trino.call_args_list[-1].kwargs.get("attempts_left"), 0)
        self.assertEqual(mock_trino.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_check_for_matching_enabled_keys_no_matches(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        with schema_context(self.schema):
            EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS).delete()
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertFalse(value)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_check_for_matching_enabled_keys(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertTrue(value)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_raw_sql_query")
    @patch("masu.database.aws_report_db_accessor.is_ocp_savings_plan_cost_enabled")
    def test_back_populate_ocp_infrastructure_costs(self, mock_unleash, mock_execute):
        """Test that we back populate raw cost to OCP."""
        is_savingsplan_cost = True
        mock_unleash.return_value = is_savingsplan_cost
        report_period_id = 1

        start_date = self.dh.this_month_start
        end_date = self.dh.today

        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpaws_ocp_infrastructure_back_populate.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
            "is_savingsplan_cost": is_savingsplan_cost,
        }

        mock_jinja = Mock()

        mock_jinja.return_value = sql, sql_params
        accessor = AWSReportDBAccessor(schema=self.schema)
        accessor.prepare_query = mock_jinja
        accessor.back_populate_ocp_infrastructure_costs(start_date, end_date, report_period_id)
        accessor.prepare_query.assert_called_with(sql, sql_params)
        mock_execute.assert_called()

        mock_jinja.reset_mock()
        mock_execute.reset_mock()
        mock_unleash.reset_mock()
        is_savingsplan_cost = False
        mock_unleash.return_value = is_savingsplan_cost
        accessor.back_populate_ocp_infrastructure_costs(start_date, end_date, report_period_id)

        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
            "is_savingsplan_cost": is_savingsplan_cost,
        }

        accessor.prepare_query.assert_called_with(sql, sql_params)
        mock_execute.assert_called()

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_raw_sql_query")
    def test_truncate_partition(self, mock_query):
        """Test that the truncate partition method works."""

        with self.assertLogs("masu.database.report_db_accessor_base", level="WARNING") as log:
            bad_partition_name = "table_without_date_partition"
            expected = "Invalid paritition provided. No TRUNCATE performed."
            self.accessor.truncate_partition(bad_partition_name)
            self.assertIn(expected, log.output[0])
            mock_query.assert_not_called()

        partition_name = "table_name_2023_03"
        self.accessor.truncate_partition(partition_name)
        mock_query.assert_called()

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_delete_aws_hive_partition_by_month(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        table = "reporting_ocpawscostlineitem_project_daily_summary_temp"
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with patch(
            "masu.database.report_db_accessor_base.ReportDBAccessorBase.schema_exists_trino", return_value=True
        ):
            with self.assertRaises(TrinoExternalError):
                self.accessor.delete_hive_partition_by_month(table, self.ocp_provider_uuid, "2022", "01")
            mock_trino.assert_called()
            # Confirms that the error log would be logged on last attempt
            self.assertEqual(mock_trino.call_args_list[-1].kwargs.get("attempts_left"), 0)
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
