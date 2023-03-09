#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AzureReportDBAccessor utility object."""
import decimal
from unittest import skip
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.db.models import F
from django.db.models import Max
from django.db.models import Min
from django.db.models import Sum
from tenant_schemas.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.utils import DateHelper
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.util.azure.common import get_bills_from_provider
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import AzureEnabledTagKeys
from reporting.provider.azure.models import AzureTagsSummary


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
        product_id = self.creator.create_azure_cost_entry_product(provider_uuid=self.azure_provider_uuid)
        bill_id = self.creator.create_azure_cost_entry_bill(provider_uuid=self.azure_provider_uuid)
        meter_id = self.creator.create_azure_meter(provider_uuid=self.azure_provider_uuid)
        self.creator.create_azure_cost_entry_line_item(bill_id, product_id, meter_id)

    def test_bills_for_provider_uuid(self):
        """Test that bills_for_provider_uuid returns the right bills."""
        bills = self.accessor.bills_for_provider_uuid(self.azure_provider_uuid, start_date=self.dh.this_month_start)
        with schema_context(self.schema):
            self.assertEqual(len(bills), 1)

    def test_populate_markup_cost(self):
        """Test that the daily summary table is populated."""
        summary_table_name = AZURE_REPORT_TABLE_MAP["line_item_daily_summary"]
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider_uuid)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills.all()]
            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            start_date = summary_entry["usage_start__min"]
            end_date = summary_entry["usage_start__max"]

        query = self.accessor._get_db_obj_query(summary_table_name)
        with schema_context(self.schema):
            expected_markup = query.filter(cost_entry_bill__in=bill_ids).aggregate(
                markup=Sum(F("pretax_cost") * decimal.Decimal(0.1))
            )
            expected_markup = expected_markup.get("markup")

        query = self.accessor._get_db_obj_query(summary_table_name)

        self.accessor.populate_markup_cost(
            self.azure_provider_uuid, decimal.Decimal(0.1), start_date, end_date, bill_ids
        )
        with schema_context(self.schema):
            query = (
                self.accessor._get_db_obj_query(summary_table_name)
                .filter(cost_entry_bill__in=bill_ids)
                .aggregate(Sum("markup_cost"))
            )
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    @skip("Revisit this test")
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
        cluster_id = self.ocp_on_azure_ocp_provider.authentication.credentials.get("cluster_id")

        self.accessor.populate_ocp_on_azure_cost_daily_summary(last_month, today, cluster_id, bill_ids, markup_value)

        li_table_name = AZURE_REPORT_TABLE_MAP["line_item"]
        with schema_context(self.schema):
            li_table = getattr(self.accessor.report_schema, li_table_name)
            sum_azure_cost = li_table.objects.aggregate(Sum("pretax_cost"))["pretax_cost__sum"]

        with schema_context(self.schema):
            # These names are defined in the `azure_static_data.yml` used by Nise to populate the Azure data
            namespaces = ["kube-system", "openshift", "banking", "mobile", "news-site", "weather"]
            for namespace in namespaces:
                with self.subTest(namespace=namespace):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"""
                            SELECT sum(pretax_cost / cardinality(namespace)) AS pretax_cost
                            FROM {summary_table._meta.db_table}
                            WHERE namespace @> array['{namespace}'::varchar]
                            """
                        )
                        sum_cost = cursor.fetchone()[0]

                    sum_project_cost = project_table.objects.filter(namespace=namespace).aggregate(
                        Sum("pretax_cost")
                    )[  # noqa: E501
                        "pretax_cost__sum"
                    ]
                    self.assertNotEqual(sum_cost, 0)
                    self.assertAlmostEqual(sum_cost, sum_project_cost, 4)
                    self.assertLessEqual(sum_cost, sum_azure_cost)

        with schema_context(self.schema):
            sum_cost = summary_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("pretax_cost"))[
                "pretax_cost__sum"
            ]
            sum_markup_cost = summary_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("markup_cost"))[
                "markup_cost__sum"
            ]
            sum_project_cost = project_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("pretax_cost"))[
                "pretax_cost__sum"
            ]
            sum_pod_cost = project_table.objects.filter(cluster_id=cluster_id).aggregate(Sum("pod_cost"))[
                "pod_cost__sum"
            ]
            sum_markup_cost_project = project_table.objects.filter(cluster_id=cluster_id).aggregate(
                Sum("markup_cost")
            )["markup_cost__sum"]
            sum_project_markup_cost_project = project_table.objects.filter(cluster_id=cluster_id).aggregate(
                Sum("project_markup_cost")
            )["project_markup_cost__sum"]

            self.assertLessEqual(sum_cost, sum_azure_cost)
            self.assertAlmostEqual(sum_markup_cost, sum_cost * markup_value, 4)
            self.assertAlmostEqual(sum_markup_cost_project, sum_project_cost * markup_value, 4)
            self.assertAlmostEqual(sum_project_markup_cost_project, sum_pod_cost * markup_value, 4)

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_raw_sql_query")
    def test_populate_line_item_daily_summary_table_presto(self, mock_presto):
        """Test that we construst our SQL and query using Presto."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.azure_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100

        self.accessor.populate_line_item_daily_summary_table_presto(
            start_date, end_date, self.azure_provider_uuid, current_bill_id, markup_value
        )
        mock_presto.assert_called()

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_raw_sql_query")
    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_multipart_sql_query")
    def test_populate_ocp_on_azure_cost_daily_summary_presto(self, mock_presto, mock_delete):
        """Test that we construst our SQL and query using Presto."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.get_cost_entry_bills_query_by_provider(self.azure_provider.uuid)
        with schema_context(self.schema):
            current_bill_id = bills.first().id if bills else None

        with CostModelDBAccessor(self.schema, self.aws_provider.uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup_value = float(markup.get("value", 0)) / 100
            distribution = cost_model_accessor.distribution_info.get("distribution_type", "cpu")

        self.accessor.populate_ocp_on_azure_cost_daily_summary_presto(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.azure_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_presto.assert_called()
        mock_delete.assert_called()

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_raw_sql_query")
    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_multipart_sql_query")
    def test_populate_ocp_on_azure_cost_daily_summary_presto_memory_distribution(self, mock_presto, mock_delete):
        """Test that we construst our SQL and query using Presto."""
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

        self.accessor.populate_ocp_on_azure_cost_daily_summary_presto(
            start_date,
            end_date,
            self.ocp_provider_uuid,
            self.azure_provider_uuid,
            self.ocp_cluster_id,
            current_bill_id,
            markup_value,
            distribution,
        )
        mock_presto.assert_called()
        mock_delete.assert_called()

    def test_populate_enabled_tag_keys(self):
        """Test that enabled tag keys are populated."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.azure_provider_uuid, start_date)
        with schema_context(self.schema):
            AzureTagsSummary.objects.all().delete()
            AzureEnabledTagKeys.objects.all().delete()
            bill_ids = [bill.id for bill in bills]
            self.assertEqual(AzureEnabledTagKeys.objects.count(), 0)
            self.accessor.populate_enabled_tag_keys(start_date, end_date, bill_ids)
            self.assertNotEqual(AzureEnabledTagKeys.objects.count(), 0)

    def test_update_line_item_daily_summary_with_enabled_tags(self):
        """Test that we filter the daily summary table's tags with only enabled tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        bills = self.accessor.bills_for_provider_uuid(self.azure_provider_uuid, start_date)
        with schema_context(self.schema):
            AzureTagsSummary.objects.all().delete()
            key_to_keep = AzureEnabledTagKeys.objects.filter(key="app").first()
            AzureEnabledTagKeys.objects.all().update(enabled=False)
            AzureEnabledTagKeys.objects.filter(key="app").update(enabled=True)
            bill_ids = [bill.id for bill in bills]
            self.accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, bill_ids)
            tags = (
                AzureCostEntryLineItemDailySummary.objects.filter(
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
            start_date = AzureCostEntryLineItemDailySummary.objects.aggregate(Max("usage_start")).get(
                "usage_start__max"
            )
            end_date = start_date

        table_query = AzureCostEntryLineItemDailySummary.objects.filter(
            source_uuid=self.azure_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
        )
        with schema_context(self.schema):
            self.assertNotEqual(table_query.count(), 0)

        self.accessor.delete_line_item_daily_summary_entries_for_date_range(
            self.azure_provider_uuid, start_date, end_date
        )

        with schema_context(self.schema):
            self.assertEqual(table_query.count(), 0)

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

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_raw_sql_query")
    def test_get_openshift_on_cloud_matched_tags_trino(self, mock_presto):
        """Test that Trino is used to find matched tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        self.accessor.get_openshift_on_cloud_matched_tags_trino(
            self.azure_provider_uuid, [self.ocp_on_azure_ocp_provider.uuid], start_date, end_date
        )
        mock_presto.assert_called()

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor.table_exists_trino")
    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_raw_sql_query")
    def test_delete_ocp_on_azure_hive_partition_by_day(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with self.assertRaises(TrinoExternalError):
            self.accessor.delete_ocp_on_azure_hive_partition_by_day(
                [1], self.azure_provider_uuid, self.ocp_provider_uuid, "2022", "01"
            )
        mock_trino.assert_called()
        # Confirms that the error log would be logged on last attempt
        self.assertEqual(mock_trino.call_args_list[-1].kwargs.get("attempts_left"), 0)
        self.assertEqual(mock_trino.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_raw_sql_query")
    def test_check_for_matching_enabled_keys_no_matches(self, mock_presto):
        """Test that Trino is used to find matched tags."""
        with schema_context(self.schema):
            AzureEnabledTagKeys.objects.all().delete()
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertFalse(value)

    @patch("masu.database.azure_report_db_accessor.AzureReportDBAccessor._execute_presto_raw_sql_query")
    def test_check_for_matching_enabled_keys(self, mock_presto):
        """Test that Trino is used to find matched tags."""
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertTrue(value)
