#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWSReportDBAccessor utility object."""
import datetime
import decimal
import os
import pkgutil
import random
from decimal import Decimal
from unittest.mock import Mock
from unittest.mock import patch

import django.apps
from dateutil import relativedelta
from django.conf import settings
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

from api.metrics.constants import DEFAULT_DISTRIBUTION_TYPE
from api.utils import DateHelper
from koku.database import get_model
from koku.database_exc import ExtendedDBException
from masu.database import AWS_CUR_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_db_accessor_base import ReportSchema
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from reporting.provider.aws.models import AWSCostEntryLineItemDailySummary
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.aws.models import AWSTagsSummary
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummaryP
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
        self.creator.create_cost_entry_pricing()
        self.creator.create_cost_entry_product()

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_get_db_obj_query_default(self):
        """Test that a query is returned."""
        table_name = random.choice(self.all_tables)
        query = self.accessor._get_db_obj_query(table_name)
        self.assertIsInstance(query, QuerySet)

    def test_get_db_obj_query_with_columns(self):
        """Test that a query is returned with limited columns."""
        tested = False
        for table_name in self.foreign_key_tables:
            columns = list(REPORT_COLUMN_MAP[table_name].values())

            selected_columns = [random.choice(columns) for _ in range(2)]
            missing_columns = set(columns).difference(selected_columns)

            query = self.accessor._get_db_obj_query(table_name, columns=selected_columns)
            with schema_context(self.schema):
                self.assertIsInstance(query, QuerySet)
                result = query.first()
                if result:
                    for column in selected_columns:
                        self.assertTrue(column in result)
                    for column in missing_columns:
                        self.assertFalse(column in result)
                    tested = True
        self.assertTrue(tested)

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
            self.assertEqual(len(bills), 1)
            self.assertEqual(bills[0].id, bill2.id)

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

        self.accessor.populate_markup_cost(
            self.aws_provider.uuid, decimal.Decimal(0.1), start_date, end_date, bill_ids
        )
        with schema_context(self.schema):
            query = (
                self.accessor._get_db_obj_query(summary_table_name)
                .filter(cost_entry_bill__in=bill_ids)
                .aggregate(Sum("markup_cost"))
            )
            actual_markup = query.get("markup_cost__sum")
            self.assertAlmostEqual(actual_markup, expected_markup, 6)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_line_item_daily_summary_table_trino(self, mock_trino):
        """Test that we construst our SQL and query using Trino."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

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

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.delete_ocp_on_aws_hive_partition_by_day")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_aws_cost_daily_summary_trino(self, mock_trino, mock_delete):
        """Test that we construst our SQL and query using Trino."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

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
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_ocp_on_aws_cost_daily_summary_trino_memory_distribution(self, mock_trino, mock_delete):
        """Test that we construst our SQL and query using Trino."""
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
            key_to_keep = AWSEnabledTagKeys.objects.filter(key="app").first()
            AWSEnabledTagKeys.objects.all().update(enabled=False)
            AWSEnabledTagKeys.objects.filter(key="app").update(enabled=True)
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
            cluster_ids = OCPAWSCostLineItemProjectDailySummaryP.objects.values_list("cluster_id").distinct()
            cluster_ids = [cluster_id[0] for cluster_id in cluster_ids]

            table_query = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                source_uuid=self.aws_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
            )
            row_count = table_query.count()

            # Change the cluster on some rows
            update_uuids = table_query.values_list("uuid")[0 : round(row_count / 2, 2)]
            table_query.filter(uuid__in=update_uuids).update(cluster_id=new_cluster_id)

            self.assertNotEqual(row_count, 0)

        self.accessor.delete_line_item_daily_summary_entries_for_date_range(
            self.aws_provider_uuid,
            start_date,
            end_date,
            table=OCPAWSCostLineItemProjectDailySummaryP,
            filters={"cluster_id": cluster_ids[0]},
        )

        with schema_context(self.schema):
            # Make sure we didn't delete everything
            table_query = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                source_uuid=self.aws_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
            )
            self.assertNotEqual(table_query.count(), 0)

            # Make sure we didn't delete this cluster
            table_query = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
                source_uuid=self.aws_provider_uuid,
                usage_start__gte=start_date,
                usage_start__lte=end_date,
                cluster_id=new_cluster_id,
            )
            self.assertNotEqual(table_query.count(), 0)

            # Make sure we deleted this cluster
            table_query = OCPAWSCostLineItemProjectDailySummaryP.objects.filter(
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

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor.table_exists_trino")
    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_delete_ocp_on_aws_hive_partition_by_day(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
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
            AWSEnabledTagKeys.objects.all().delete()
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertFalse(value)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_check_for_matching_enabled_keys(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        value = self.accessor.check_for_matching_enabled_keys()
        self.assertTrue(value)

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_raw_sql_query")
    @patch("masu.database.aws_report_db_accessor.enable_ocp_savings_plan_cost")
    def test_back_populate_ocp_infrastructure_costs(self, mock_unleash, mock_execute):
        """Test that we back populate raw cost to OCP."""
        is_savingsplan_cost = True
        mock_unleash.return_value = is_savingsplan_cost
        report_period_id = 1
        dh = DateHelper()

        start_date = dh.this_month_start
        end_date = dh.today

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

        mock_jinja.prepare_query.return_value = sql, sql_params
        accessor = AWSReportDBAccessor(schema=self.schema)
        accessor.jinja_sql = mock_jinja
        accessor.back_populate_ocp_infrastructure_costs(start_date, end_date, report_period_id)
        accessor.jinja_sql.prepare_query.assert_called_with(sql, sql_params)
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

        accessor.jinja_sql.prepare_query.assert_called_with(sql, sql_params)
        mock_execute.assert_called()

    @patch("masu.database.aws_report_db_accessor.AWSReportDBAccessor._execute_trino_raw_sql_query")
    def test_check_for_invoice_id_trino(self, mock_trino):
        """Check that an invoice ID exists or not."""
        mock_trino.return_value = [
            ("1",),
        ]
        expected = ["1"]
        check_date = DateHelper().today
        invoice_ids = self.accessor.check_for_invoice_id_trino(str(self.aws_provider.uuid), check_date)

        self.assertEqual(invoice_ids, expected)

        mock_trino.reset_mock()

        mock_trino.return_value = [
            ("",),
        ]
        expected = []
        check_date = DateHelper().today
        invoice_ids = self.accessor.check_for_invoice_id_trino(str(self.aws_provider.uuid), check_date)

        self.assertEqual(invoice_ids, expected)

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
