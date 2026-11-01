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
from django.db import connection
from django.db import DatabaseError
from django.db import transaction
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from django.db.utils import ProgrammingError
from django_tenants.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.provider.models import Provider
from koku.database import get_model
from koku.trino_database import TrinoHiveMetastoreError
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.test import MasuTestCase
from reporting.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.aws.models import AWSCostEntryBill
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSCostEntryLineItemSummaryByEC2ComputeP


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

        with CostModelDBAccessor(
            self.schema, self.aws_provider.uuid, price_list_effective_on=None
        ) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_line_item_daily_summary_table_trino(
            start_date, end_date, self.aws_provider_uuid, current_bill_id, markup_value
        )
        mock_trino.assert_called()

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_ocp_on_aws_ui_summary_tables_trino_managed(self, mock_trino):
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
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._get_matched_tags_strings")
    def test_populate_ocp_on_aws_cost_daily_summary_trino_managed(
        self, mock_get_tags, mock_trino, mock_month_delete, mock_delete
    ):
        """Test that we construst our SQL and query using Trino."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        mock_get_tags.return_value = "fake-tags"

        self.accessor.populate_ocp_on_aws_cost_daily_summary_trino(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.aws_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
        )
        mock_trino.assert_called()

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
    @patch("masu.database.report_db_accessor_base.trino_db.connect")
    @patch("time.sleep", return_value=None)
    def test_delete_ocp_on_aws_hive_partition_by_day(
        self, mock_sleep, mock_connect, mock_table_exists, mock_schema_exists
    ):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_ocp_on_aws_hive_partition_by_day(
            [1], self.aws_provider_uuid, self.ocp_provider_uuid, "2022", "01"
        )
        mock_connect.assert_not_called()

        mock_connect.reset_mock()

        mock_schema_exists.return_value = True
        attrs = {"cursor.side_effect": TrinoExternalError({"errorName": "HIVE_METASTORE_ERROR"})}
        mock_connect.return_value = Mock(**attrs)

        with self.assertRaises(TrinoHiveMetastoreError):
            self.accessor.delete_ocp_on_aws_hive_partition_by_day(
                [1], self.aws_provider_uuid, self.ocp_provider_uuid, "2022", "01"
            )

        mock_connect.assert_called()
        self.assertEqual(mock_connect.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.schema_exists_trino")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.trino_db.connect")
    @patch("time.sleep", return_value=None)
    def test_delete_ocp_on_aws_hive_partition_by_day_managed_table(
        self, mock_sleep, mock_connect, mock_table_exists, mock_schema_exists
    ):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_ocp_on_aws_hive_partition_by_day(
            [1],
            self.aws_provider_uuid,
            self.ocp_provider_uuid,
            "2022",
            "01",
        )
        mock_connect.assert_not_called()

        mock_connect.reset_mock()

        mock_schema_exists.return_value = True
        attrs = {"cursor.side_effect": TrinoExternalError({"errorName": "HIVE_METASTORE_ERROR"})}
        mock_connect.return_value = Mock(**attrs)

        with self.assertRaises(TrinoHiveMetastoreError):
            self.accessor.delete_ocp_on_aws_hive_partition_by_day(
                [1],
                self.aws_provider_uuid,
                self.ocp_provider_uuid,
                "2022",
                "01",
            )

        mock_connect.assert_called()
        self.assertEqual(mock_connect.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

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
    def test_back_populate_ocp_infrastructure_costs(self, mock_execute):
        """Test that we back populate raw cost to OCP."""
        report_period_id = 1
        start_date = self.dh.this_month_start
        end_date = self.dh.today
        sql = pkgutil.get_data(
            "masu.database", "sql/aws/openshift/reporting_ocpaws_ocp_infrastructure_back_populate.sql"
        )
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
        }

        mock_jinja = Mock()
        mock_jinja.return_value = sql, sql_params
        accessor = AWSReportDBAccessor(schema=self.schema)
        accessor.prepare_query = mock_jinja
        accessor.back_populate_ocp_infrastructure_costs(start_date, end_date, report_period_id)

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

    def test_update_line_item_daily_summary_with_tag_mapping(self):
        """
        Test that mapped tags are updated in aws line item summary tables.
        After the update, the child tag's key-value data is cleared and the parent tag's data is updated accordingly.
        """
        populated_keys = []

        table_classes = [AWSCostEntryLineItemDailySummary, AWSCostEntryLineItemSummaryByEC2ComputeP]

        for table_class in table_classes:
            with self.subTest(table_class=table_class):
                populated_keys = []
                with schema_context(self.schema):
                    enabled_tags = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS, enabled=True)
                    for enabled_tag in enabled_tags:
                        tag_count = table_class.objects.filter(
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
                    self.accessor.update_line_item_daily_summary_with_tag_mapping(
                        self.dh.this_month_start, self.dh.today, table_name=table_class._meta.db_table
                    )
                    expected_parent_count = parent_count + child_count
                    actual_parent_count = table_class.objects.filter(
                        tags__has_key=parent_key,
                        usage_start__gte=self.dh.this_month_start,
                        usage_start__lte=self.dh.today,
                    ).count()
                    self.assertEqual(expected_parent_count, actual_parent_count)
                    actual_child_count = table_class.objects.filter(
                        tags__has_key=child_key,
                        usage_start__gte=self.dh.this_month_start,
                        usage_start__lte=self.dh.today,
                    ).count()
                    self.assertEqual(0, actual_child_count)

                    # Clear TagMapping objects
                    TagMapping.objects.filter(parent=parent_obj, child=child_obj).delete()

    def test_populate_ocp_on_aws_tag_information(self):
        """
        This tests the tag mapping feature.
        """
        populated_keys = []
        report_period_id = 1
        with schema_context(self.schema):
            enabled_tags = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS, enabled=True)
            for enabled_tag in enabled_tags:
                tag_count = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                    tags__has_key=enabled_tag.key,
                    usage_start__gte=self.dh.this_month_start,
                    usage_start__lte=self.dh.today,
                ).count()
                if tag_count > 0:
                    key_metadata = [enabled_tag.key, enabled_tag, tag_count]
                    populated_keys.append(key_metadata)
                if len(populated_keys) == 2:
                    break
            bill_ids = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=enabled_tag.key,
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today,
            ).values_list("cost_entry_bill", flat=True)
            parent_key, parent_obj, parent_count = populated_keys[0]
            child_key, child_obj, child_count = populated_keys[1]
            TagMapping.objects.create(parent=parent_obj, child=child_obj)
            self.accessor.populate_ocp_on_aws_tag_information(
                bill_ids, self.dh.this_month_start, self.dh.today, report_period_id
            )
            expected_parent_count = parent_count + child_count
            actual_parent_count = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=parent_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(expected_parent_count, actual_parent_count)
            actual_child_count = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                tags__has_key=child_key, usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).count()
            self.assertEqual(0, actual_child_count)

    def test_ocp_on_aws_tag_mapping_guardrail_flags(self):
        """The existing flags independently control the AWS plan fence and leaf ANALYZE."""
        with schema_context(self.schema):
            parent, child = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS, enabled=True)[:2]
            TagMapping.objects.create(parent=parent, child=child)

        for analyze_enabled, materialize_enabled in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(analyze=analyze_enabled, materialize=materialize_enabled):

                def flag_enabled(schema, flag, **kwargs):
                    if flag.endswith("ocp_tag_mapping_pre_analyze"):
                        return analyze_enabled
                    if flag.endswith("ocp_tag_mapping_materialized_candidates"):
                        return materialize_enabled
                    return False

                with (
                    patch(
                        "masu.database.aws_report_db_accessor.is_feature_flag_enabled_by_schema",
                        side_effect=flag_enabled,
                    ),
                    patch.object(self.accessor, "_prepare_and_execute_raw_sql_query") as execute,
                    patch.object(self.accessor, "_analyze_tag_mapping_partition") as analyze,
                ):
                    self.accessor.populate_ocp_on_aws_tag_information([1], self.dh.this_month_start, self.dh.today, 1)

                self.assertEqual(execute.call_count, 2)
                mapping_call = next(call for call in execute.call_args_list if "cte_update_tag_keys" in call.args[1])
                sql = mapping_call.args[1]
                params = mapping_call.args[2]
                rendered, bind_params = self.accessor.prepare_query(sql, params)
                self.assertEqual("cte_update_tag_keys as MATERIALIZED (" in rendered, materialize_enabled)
                self.assertEqual("cte_update_tag_keys as (" in rendered, not materialize_enabled)
                self.assertIn("cost_entry_bill_id in", rendered)
                if materialize_enabled:
                    with connection.cursor() as cursor:
                        cursor.db.set_schema(self.schema)
                        cursor.execute(f"EXPLAIN (FORMAT JSON) {rendered}", params=bind_params)
                        plan = cursor.fetchone()[0][0]["Plan"]
                    pending = [plan]
                    nodes = []
                    while pending:
                        node = pending.pop()
                        nodes.append(node)
                        pending.extend(node.get("Plans", []))
                    self.assertEqual(sum(node.get("Subplan Name") == "CTE cte_update_tag_keys" for node in nodes), 1)
                    self.assertTrue(any(node.get("Node Type") == "CTE Scan" for node in nodes))
                if analyze_enabled:
                    analyze.assert_called_once_with(
                        f"{OCPAWSCostLineItemProjectDailySummaryP._meta.db_table}_{self.dh.this_month_start:%Y_%m}",
                        label="OCP-on-AWS",
                    )
                else:
                    analyze.assert_not_called()

    def test_ocp_on_aws_tag_mapping_analyze_failure_keeps_update(self):
        """A failed optional monthly ANALYZE does not suppress the mapping UPDATE."""
        with schema_context(self.schema):
            parent, child = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS, enabled=True)[:2]
            TagMapping.objects.create(parent=parent, child=child)

        start_date = self.dh.this_month_start - relativedelta.relativedelta(months=1)
        with (
            patch("masu.database.aws_report_db_accessor.is_feature_flag_enabled_by_schema", return_value=True),
            patch.object(self.accessor, "_prepare_and_execute_raw_sql_query") as execute,
            patch.object(
                self.accessor, "_analyze_tag_mapping_partition", side_effect=[DatabaseError("test"), None]
            ) as analyze,
        ):
            self.accessor.populate_ocp_on_aws_tag_information([1], start_date, self.dh.today, 1)

        self.assertEqual(analyze.call_count, 2)
        self.assertEqual(execute.call_count, 2)
        mapping_call = next(call for call in execute.call_args_list if "cte_update_tag_keys" in call.args[1])
        rendered, _ = self.accessor.prepare_query(mapping_call.args[1], mapping_call.args[2])
        self.assertIn("cte_update_tag_keys as MATERIALIZED (", rendered)

    def test_ocp_on_aws_materialization_preserves_mapped_tags(self):
        """Both SQL shapes update the same seeded rows to the same JSONB tags."""
        with schema_context(self.schema):
            enabled_tags = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS, enabled=True)
            populated = [
                key
                for key in enabled_tags
                if OCPAWSCostLineItemProjectDailySummaryP.objects.filter(tags__has_key=key.key).exists()
            ][:2]
            parent, child = populated
            TagMapping.objects.create(parent=parent, child=child)
            rows = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today,
            )
            bill_ids = list(rows.values_list("cost_entry_bill_id", flat=True).distinct())
            self.assertTrue(rows.filter(tags__has_key=child.key).exists())

            savepoint = transaction.savepoint()
            with patch("masu.database.aws_report_db_accessor.is_feature_flag_enabled_by_schema", return_value=False):
                self.accessor.populate_ocp_on_aws_tag_information(bill_ids, self.dh.this_month_start, self.dh.today, 1)
            legacy = list(rows.order_by("uuid").values_list("uuid", "usage_start", "tags"))
            transaction.savepoint_rollback(savepoint)

            def materialize_only(schema, flag, **kwargs):
                return flag.endswith("ocp_tag_mapping_materialized_candidates")

            with patch(
                "masu.database.aws_report_db_accessor.is_feature_flag_enabled_by_schema", side_effect=materialize_only
            ):
                self.accessor.populate_ocp_on_aws_tag_information(bill_ids, self.dh.this_month_start, self.dh.today, 1)
            materialized = list(rows.order_by("uuid").values_list("uuid", "usage_start", "tags"))
            self.assertEqual(materialized, legacy)
            self.assertTrue(
                any(parent.key in (tags or {}) and child.key not in (tags or {}) for _, _, tags in materialized)
            )

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_ec2_compute_summary_table_trino(self, mock_trino):
        """
        Test that we construst our SQL and query using Trino to populate AWSCostEntryLineItemSummaryByEC2ComputeP.
        """
        start_date = self.dh.this_month_start.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.aws_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(
            self.schema, self.aws_provider.uuid, price_list_effective_on=None
        ) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_ec2_compute_summary_table_trino(
            self.aws_provider_uuid, start_date, current_bill_id, markup_value
        )
        mock_trino.assert_called()

    def test_get_matched_tags_strings_postgres(self):
        """Test fetching match tag strings via postgres."""
        tags = ['"app": "mobile"']
        result = self.accessor._get_matched_tags_strings(
            1, self.aws_provider_uuid, self.ocp_provider_uuid, "2022-04-01", "2022-04-10"
        )
        self.assertEqual(tags, result)

    @patch(
        "masu.database.aws_report_db_accessor.AWSReportDBAccessor.get_openshift_on_cloud_matched_tags",
        return_value=None,
    )
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.get_openshift_on_cloud_matched_tags_trino")
    def test_get_matched_tags_strings_trino(self, mock_postgres_tags, mock_trino_tags):
        """Test fetching match tag strings via trino."""
        tags = ['"app"']
        mock_trino_tags.return_value = {"app"}
        start = self.dh.this_month_start
        end = self.dh.this_month_end
        result = self.accessor._get_matched_tags_strings(1, self.aws_provider_uuid, self.ocp_provider_uuid, start, end)
        self.assertEqual(tags, result)

    @patch(
        "masu.database.aws_report_db_accessor.AWSReportDBAccessor.get_openshift_on_cloud_matched_tags",
        return_value=None,
    )
    @patch(
        "masu.database.aws_report_db_accessor.AWSReportDBAccessor.get_openshift_on_cloud_matched_tags_trino",
        return_value=[],
    )
    def test_get_matched_tags_strings_no_tags(self, mock_postgres_tags, mock_trino_tags):
        """Test fetching match tag with no tags returned."""
        start = self.dh.this_month_start
        end = self.dh.this_month_end
        result = self.accessor._get_matched_tags_strings(1, self.aws_provider_uuid, self.ocp_provider_uuid, start, end)
        self.assertEqual([], result)

    @patch(
        "masu.database.aws_report_db_accessor.AWSReportDBAccessor.get_openshift_on_cloud_matched_tags",
        return_value=None,
    )
    @patch("masu.database.aws_report_db_accessor.is_tag_processing_disabled", return_value=True)
    def test_get_matched_tags_strings_trino_disabled(self, mock_postgres_tags, mock_unleash):
        """Test fetching match tag strings."""
        result = self.accessor._get_matched_tags_strings(
            1, self.aws_provider_uuid, self.ocp_provider_uuid, "2022-04-01", "2022-04-10"
        )
        self.assertEqual([], result)

    def test_ocp_on_aws_disk_capacity_sql_filters_ebs_volume_usage(self):
        """COST-8328: capacity CTE must only use EBS VolumeUsage CUR line items."""
        sql_template = pkgutil.get_data(
            "masu.database",
            "trino_sql/aws/openshift/populate_daily_summary/2_summarize_data_by_cluster.sql",
        )
        sql_template = sql_template.decode("utf-8")
        capacity_section = sql_template.split("calculated_capacity AS (")[1].split(
            "SELECT *\nFROM calculated_capacity"
        )[0]
        self.assertIn("lineitem_usagetype LIKE '%EBS:VolumeUsage%'", capacity_section)

    def test_ocp_on_aws_summary_uses_prunable_month_predicate(self):
        """COST-8094: avoid lpad on partition column so Trino can prune month partitions."""
        sql_template = pkgutil.get_data(
            "masu.database",
            "trino_sql/aws/openshift/populate_daily_summary/2_summarize_data_by_cluster.sql",
        )
        sql_template = sql_template.decode("utf-8")
        self.assertNotIn("lpad(ocp.month, 2, '0') = {{month}}", sql_template)
        self.assertIn(
            "ocp.month IN ({{month}}, CAST(CAST({{month}} AS integer) AS varchar))",
            sql_template,
        )
        # Unattributed storage CTE must use the prunable predicate
        unattributed = sql_template.split("cte_total_pv_capacity as (")[1].split("SELECT  cast(uuid()")[0]
        self.assertIn(
            "ocp.month IN ({{month}}, CAST(CAST({{month}} AS integer) AS varchar))",
            unattributed,
        )

    def test_matched_tags_sql_uses_prunable_month_predicate(self):
        """COST-8094: matched-tags lookups must prune month partitions."""
        for path in (
            "trino_sql/aws/openshift/reporting_ocpaws_matched_tags.sql",
            "trino_sql/openshift/ocp_special_matched_tags.sql",
        ):
            sql_template = pkgutil.get_data("masu.database", path).decode("utf-8")
            with self.subTest(path=path):
                self.assertNotIn("lpad(month, 2, '0') = {{month}}", sql_template)
                self.assertIn(
                    "month IN ({{month}}, CAST(CAST({{month}} AS integer) AS varchar))",
                    sql_template,
                )

    def test_summary_sql_metadata_days_tup_includes_padded_and_legacy(self):
        """COST-8094: days_tup dual for reads; days_delete_tup one padded value per day."""
        from datetime import date

        from masu.processor.parquet.summary_sql_metadata import SummarySqlMetadata

        metadata = SummarySqlMetadata(
            schema=self.schema,
            ocp_provider_uuid=str(self.ocp_provider_uuid),
            cloud_provider_uuid=str(self.aws_provider_uuid),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 9),
            matched_tag_strs=[],
            bill_id=1,
            report_period_id=1,
        )
        self.assertIn("01", metadata.days_tup)
        self.assertIn("1", metadata.days_tup)
        self.assertIn("09", metadata.days_tup)
        self.assertIn("9", metadata.days_tup)
        self.assertEqual(metadata.days_delete_tup, ("01", "02", "03", "04", "05", "06", "07", "08", "09"))

    def test_ocp_on_aws_disk_capacity_formula_ignores_provisioned_performance_lines(self):
        """COST-8328: provisioned throughput/IOPS rates must not drive capacity."""
        hours_in_month = 720

        def capacity_from_lines(lines, storage_only):
            if storage_only:
                lines = [line for line in lines if "EBS:VolumeUsage" in line["usagetype"]]
            max_cost = max(line["cost"] for line in lines)
            max_rate = max(line["rate"] for line in lines)
            return round(max_cost / (max_rate / hours_in_month))

        # Scenario A: 1024 GB gp3 with provisioned throughput/IOPS
        scenario_a = [
            {"usagetype": "APS2-EBS:VolumeUsage.gp3", "cost": 0.1365333333, "rate": 0.096},
            {"usagetype": "APS2-EBS:VolumeP-Throughput.gp3", "cost": 0.0116666667, "rate": 49.152},
            {"usagetype": "APS2-EBS:VolumeP-IOPS.gp3", "cost": 0.025, "rate": 0.006},
        ]
        self.assertEqual(capacity_from_lines(scenario_a, storage_only=False), 2)
        self.assertEqual(capacity_from_lines(scenario_a, storage_only=True), 1024)

        # Scenario C: ordinary 100 GB volume with $0 / nonzero-rate VolumeP-* rows
        scenario_c = [
            {"usagetype": "APS2-EBS:VolumeUsage.gp3", "cost": 0.0133333333, "rate": 0.096},
            {"usagetype": "APS2-EBS:VolumeP-Throughput.gp3", "cost": 0.0, "rate": 49.152},
            {"usagetype": "APS2-EBS:VolumeP-IOPS.gp3", "cost": 0.0, "rate": 0.006},
        ]
        self.assertEqual(capacity_from_lines(scenario_c, storage_only=False), 0)
        self.assertEqual(capacity_from_lines(scenario_c, storage_only=True), 100)
