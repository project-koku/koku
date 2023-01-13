#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportDBAccessor utility object."""
import random
import string
import uuid
from collections import defaultdict
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch

from dateutil import relativedelta
from dateutil.rrule import MONTHLY
from dateutil.rrule import rrule
from django.conf import settings
from django.db.models import Max
from django.db.models import Min
from django.db.models import Q
from django.db.models import Sum
from django.db.models.query import QuerySet
from tenant_schemas.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.iam.test.iam_test_case import FakePrestoConn
from api.metrics import constants as metric_constants
from api.utils import DateHelper
from koku import trino_database as trino_db
from koku.database import KeyDecimalTransform
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.util.common import month_date_range_tuple
from reporting.models import OCPEnabledTagKeys
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsageLineItemDailySummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.models import OCPUsageReport
from reporting.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPNode
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OCPPVC
from reporting_common import REPORT_COLUMN_MAP


class OCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the OCPReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = OCPReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema)
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

        self.cluster_id = "testcluster"
        with ProviderDBAccessor(provider_uuid=self.ocp_test_provider_uuid) as provider_accessor:
            self.ocp_provider_uuid = provider_accessor.get_provider().uuid

        self.reporting_period = self.creator.create_ocp_report_period(
            provider_uuid=self.ocp_provider_uuid, cluster_id=self.cluster_id
        )
        self.report = self.creator.create_ocp_report(self.reporting_period)
        pod = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
        namespace = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
        node = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
        self.creator.create_ocp_usage_line_item(self.reporting_period, self.report, pod=pod, namespace=namespace)
        self.creator.create_ocp_storage_line_item(self.reporting_period, self.report, pod=pod, namespace=namespace)
        self.creator.create_ocp_node_label_line_item(self.reporting_period, self.report, node=node)

    def _populate_storage_summary(self, cluster_id=None):
        """Generate storage summary data."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        report_table = getattr(self.accessor.report_schema, report_table_name)
        if cluster_id is None:
            cluster_id = self.cluster_id
        for _ in range(25):
            pod = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
            namespace = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
            self.creator.create_ocp_usage_line_item(self.reporting_period, self.report, pod=pod, namespace=namespace)
            self.creator.create_ocp_storage_line_item(self.reporting_period, self.report, pod=pod, namespace=namespace)
        self.creator.create_ocp_node_label_line_item(self.reporting_period, self.report)
        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        self.accessor.populate_node_label_line_item_daily_table(start_date, end_date, cluster_id)
        self.accessor.populate_line_item_daily_table(start_date, end_date, cluster_id)

        self.accessor.populate_storage_line_item_daily_table(start_date, end_date, cluster_id)
        self.accessor.populate_storage_line_item_daily_summary_table(
            start_date, end_date, cluster_id, self.provider_uuid
        )

    def _populate_pod_summary(self):
        """Generate pod summary data."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        report_table = getattr(self.accessor.report_schema, report_table_name)

        cluster_id = "testcluster"
        for _ in range(25):
            self.creator.create_ocp_usage_line_item(self.reporting_period, self.report)

        self.creator.create_ocp_node_label_line_item(self.reporting_period, self.report)
        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        self.accessor.populate_node_label_line_item_daily_table(start_date, end_date, cluster_id)
        self.accessor.populate_line_item_daily_table(start_date, end_date, cluster_id)
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, cluster_id, self.ocp_provider_uuid)
        return (start_date, end_date)

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
        table_name = OCP_REPORT_TABLE_MAP["line_item"]
        columns = list(REPORT_COLUMN_MAP[table_name].values())

        selected_columns = [random.choice(columns) for _ in range(2)]
        missing_columns = set(columns).difference(selected_columns)

        query = self.accessor._get_db_obj_query(table_name, columns=selected_columns)
        self.assertIsInstance(query, QuerySet)
        with schema_context(self.schema):
            result = query.first()

            for column in selected_columns:
                self.assertTrue(column in result)

            for column in missing_columns:
                self.assertFalse(column in result)

    def test_get_current_usage_report(self):
        """Test that the most recent usage report is returned."""
        current_report = self.accessor.get_current_usage_report()
        self.assertIsNotNone(current_report.interval_start)
        self.assertIsNotNone(current_report.interval_end)
        self.assertIsNotNone(current_report.report_period_id)

    def test_get_current_usage_period(self):
        """Test that the most recent usage period is returned."""
        current_report_period = self.accessor.get_current_usage_period(self.ocp_provider_uuid)
        self.assertIsNotNone(current_report_period.report_period_start)
        self.assertIsNotNone(current_report_period.report_period_end)

    def test_get_usage_periods_by_date(self):
        """Test that report periods are returned by date filter."""
        period_start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        prev_period_start = period_start - relativedelta.relativedelta(months=1)
        reporting_period = self.creator.create_ocp_report_period(self.ocp_provider_uuid, period_date=period_start)
        prev_reporting_period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid, period_date=prev_period_start
        )

        with schema_context(self.schema):
            periods = self.accessor.get_usage_periods_by_date(period_start.date())
            self.assertIn(reporting_period, periods)
            periods = self.accessor.get_usage_periods_by_date(prev_period_start.date())
            self.assertIn(prev_reporting_period, periods)

    def test_get_usage_period_by_dates_and_cluster(self):
        """Test that report periods are returned by dates & cluster filter."""
        period_start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        period_end = period_start + relativedelta.relativedelta(months=1)
        prev_period_start = period_start - relativedelta.relativedelta(months=1)
        prev_period_end = prev_period_start + relativedelta.relativedelta(months=1)
        reporting_period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid, period_date=period_start, cluster_id="0001"
        )
        prev_reporting_period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid, period_date=prev_period_start, cluster_id="0002"
        )
        with schema_context(self.schema):
            periods = self.accessor.get_usage_period_by_dates_and_cluster(
                period_start.date(), period_end.date(), "0001"
            )
            self.assertEqual(reporting_period, periods)
            periods = self.accessor.get_usage_period_by_dates_and_cluster(
                prev_period_start.date(), prev_period_end.date(), "0002"
            )
            self.assertEqual(prev_reporting_period, periods)

    def test_get_usage_period_query_by_provider(self):
        """Test that periods are returned filtered by provider."""
        provider_uuid = self.ocp_provider_uuid

        period_query = self.accessor.get_usage_period_query_by_provider(provider_uuid)
        with schema_context(self.schema):
            periods = period_query.all()

            self.assertGreater(len(periods), 0)

            period = periods[0]

            self.assertEqual(period.provider_id, provider_uuid)

    def test_report_periods_for_provider_uuid(self):
        """Test that periods are returned filtered by provider id and start date."""
        provider_uuid = self.ocp_provider_uuid
        start_date = str(self.reporting_period.report_period_start)

        period = self.accessor.report_periods_for_provider_uuid(provider_uuid, start_date)
        with schema_context(self.schema):
            self.assertEqual(period.provider_id, provider_uuid)

    def test_populate_line_item_daily_table(self):
        """Test that the line item daily table populates."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        daily_table_name = OCP_REPORT_TABLE_MAP["line_item_daily"]

        report_table = getattr(self.accessor.report_schema, report_table_name)
        daily_table = getattr(self.accessor.report_schema, daily_table_name)

        for _ in range(25):
            self.creator.create_ocp_usage_line_item(self.reporting_period, self.report)

        self.creator.create_ocp_node_label_line_item(self.reporting_period, self.report)
        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(daily_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_node_label_line_item_daily_table(start_date, end_date, self.cluster_id)
        self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)

        self.assertNotEqual(query.count(), initial_count)

        with schema_context(self.schema):
            daily_entry = daily_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = daily_entry["usage_start__min"]
            result_end_date = daily_entry["usage_start__max"]

        self.assertEqual(result_start_date, start_date.date())
        self.assertEqual(result_end_date, end_date.date())

        with schema_context(self.schema):
            entry = query.first()

            summary_columns = [
                "cluster_id",
                "namespace",
                "node",
                "node_capacity_cpu_core_seconds",
                "node_capacity_cpu_cores",
                "node_capacity_memory_byte_seconds",
                "node_capacity_memory_bytes",
                "pod",
                "pod_labels",
                "pod_limit_cpu_core_seconds",
                "pod_limit_memory_byte_seconds",
                "pod_request_cpu_core_seconds",
                "pod_request_memory_byte_seconds",
                "pod_usage_cpu_core_seconds",
                "pod_usage_memory_byte_seconds",
                "total_seconds",
                "usage_end",
                "usage_start",
            ]

            for column in summary_columns:
                self.assertIsNotNone(getattr(entry, column))

    def test_get_usage_period_on_or_before_date(self):
        """Test that gets a query for usage report periods before a date."""
        with schema_context(self.schema):
            # Verify that the result is returned for cutoff_date == report_period_start
            cutoff_date = DateHelper().this_month_start
            report_period_count = OCPUsageReportPeriod.objects.filter(report_period_start__lte=cutoff_date).count()
            usage_period = self.accessor.get_usage_period_on_or_before_date(cutoff_date)
            self.assertEqual(usage_period.count(), report_period_count)
            self.assertLess(usage_period.first().report_period_start, cutoff_date)

            # Verify that the result is returned for a date later than cutoff_date
            later_cutoff = cutoff_date + relativedelta.relativedelta(months=+1)
            # later_cutoff = later_date.replace(month=later_date.month, day=15)
            report_period_count = OCPUsageReportPeriod.objects.filter(report_period_start__lte=later_cutoff).count()
            usage_period = self.accessor.get_usage_period_on_or_before_date(later_cutoff)
            self.assertEqual(usage_period.count(), report_period_count)
            self.assertLessEqual(usage_period.first().report_period_start, cutoff_date)

            # Verify that no results are returned for a date earlier than cutoff_date
            earlier_date = cutoff_date + relativedelta.relativedelta(months=-5)
            earlier_cutoff = earlier_date.replace(month=earlier_date.month, day=15)
            usage_period = self.accessor.get_usage_period_on_or_before_date(earlier_cutoff)
            self.assertEqual(usage_period.count(), 0)

    def test_get_pod_cpu_core_hours(self):
        """Test that gets pod cpu usage/request."""
        start_date, end_date = self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        # Verify that the line items for the test cluster_id are returned
        cluster_id = self.accessor._get_db_obj_query(table_name).first().cluster_id
        reports = self.accessor._get_db_obj_query(table_name).filter(
            cluster_id=cluster_id, usage_start__gte=start_date, usage_start__lte=end_date, data_source="Pod"
        )

        expected_usage_reports = {entry.uuid: entry.pod_usage_cpu_core_hours for entry in reports}
        expected_request_reports = {entry.uuid: entry.pod_usage_cpu_core_hours for entry in reports}
        cpu_usage_query = self.accessor.get_pod_usage_cpu_core_hours(start_date, end_date, cluster_id)
        cpu_request_query = self.accessor.get_pod_request_cpu_core_hours(start_date, end_date, cluster_id)

        self.assertEqual(len(cpu_usage_query.keys()), len(expected_usage_reports.keys()))
        self.assertEqual(len(cpu_request_query.keys()), len(expected_request_reports.keys()))

        # Verify that no line items are returned for an incorrect cluster_id
        wrong_cluster_id = cluster_id + "bad"
        cpu_usage_query = self.accessor.get_pod_usage_cpu_core_hours(start_date, end_date, wrong_cluster_id)
        self.assertEqual(len(cpu_usage_query.keys()), 0)
        cpu_request_query = self.accessor.get_pod_request_cpu_core_hours(start_date, end_date, wrong_cluster_id)
        self.assertEqual(len(cpu_request_query.keys()), 0)

    def test_get_pod_cpu_core_hours_no_cluster_id(self):
        """Test that gets pod cpu usage/request without cluster id."""
        start_date, end_date = self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        # Verify that the line items for the test cluster_id are returned
        reports = (
            self.accessor._get_db_obj_query(table_name)
            .filter(usage_start__gte=start_date, usage_end__lte=end_date, data_source="Pod")
            .all()
        )

        expected_usage_reports = {entry.uuid: entry.pod_usage_cpu_core_hours for entry in reports}
        expected_request_reports = {entry.uuid: entry.pod_usage_cpu_core_hours for entry in reports}
        cpu_usage_query = self.accessor.get_pod_usage_cpu_core_hours(start_date, end_date)
        cpu_request_query = self.accessor.get_pod_request_cpu_core_hours(start_date, end_date)

        self.assertEqual(len(cpu_usage_query.keys()), len(expected_usage_reports.keys()))
        self.assertEqual(len(cpu_request_query.keys()), len(expected_request_reports.keys()))

    def test_get_pod_memory_gigabyte_hours(self):
        """Test that gets pod memory usage/request."""
        start_date, end_date = self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        # Verify that the line items for the test cluster_id are returned
        cluster_id = self.accessor._get_db_obj_query(table_name).first().cluster_id
        reports = self.accessor._get_db_obj_query(table_name).filter(
            cluster_id=cluster_id, usage_start__gte=start_date, usage_start__lte=end_date, data_source="Pod"
        )

        expected_usage_reports = {entry.uuid: entry.pod_usage_memory_gigabyte_hours for entry in reports}
        expected_request_reports = {entry.uuid: entry.pod_request_memory_gigabyte_hours for entry in reports}
        mem_usage_query = self.accessor.get_pod_usage_memory_gigabyte_hours(start_date, end_date, cluster_id)
        mem_request_query = self.accessor.get_pod_request_memory_gigabyte_hours(start_date, end_date, cluster_id)

        self.assertEqual(len(mem_usage_query.keys()), len(expected_usage_reports.keys()))
        self.assertEqual(len(mem_request_query.keys()), len(expected_request_reports.keys()))

        # Verify that no line items are returned for an incorrect cluster_id
        wrong_cluster_id = cluster_id + "bad"
        mem_usage_query = self.accessor.get_pod_usage_cpu_core_hours(start_date, end_date, wrong_cluster_id)
        self.assertEqual(len(mem_usage_query.keys()), 0)
        mem_request_query = self.accessor.get_pod_usage_cpu_core_hours(start_date, end_date, wrong_cluster_id)
        self.assertEqual(len(mem_request_query.keys()), 0)

    def test_get_pod_memory_gigabyte_hours_no_cluster_id(self):
        """Test that gets pod memory usage/request without cluster id."""
        start_date, end_date = self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        # Verify that the line items for the test cluster_id are returned
        reports = (
            self.accessor._get_db_obj_query(table_name)
            .filter(usage_start__gte=start_date, usage_end__lte=end_date, data_source="Pod")
            .all()
        )

        expected_usage_reports = {entry.uuid: entry.pod_usage_memory_gigabyte_hours for entry in reports}
        expected_request_reports = {entry.uuid: entry.pod_request_memory_gigabyte_hours for entry in reports}
        mem_usage_query = self.accessor.get_pod_usage_memory_gigabyte_hours(start_date, end_date)
        mem_request_query = self.accessor.get_pod_request_memory_gigabyte_hours(start_date, end_date)

        self.assertEqual(len(mem_usage_query.keys()), len(expected_usage_reports.keys()))
        self.assertEqual(len(mem_request_query.keys()), len(expected_request_reports.keys()))

    def test_get_volume_gigabyte_months(self):
        """Test that gets pod volume usage/request."""
        start_date, end_date = self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        # Verify that the line items for the test cluster_id are returned
        reports = self.accessor._get_db_obj_query(table_name).filter(cluster_id=self.cluster_id, data_source="Storage")

        expected_usage_reports = {entry.uuid: entry.persistentvolumeclaim_usage_gigabyte_months for entry in reports}
        expected_request_reports = {entry.uuid: entry.volume_request_storage_gigabyte_months for entry in reports}
        vol_usage_query = self.accessor.get_persistentvolumeclaim_usage_gigabyte_months(
            start_date, end_date, self.cluster_id
        )
        vol_request_query = self.accessor.get_volume_request_storage_gigabyte_months(
            start_date, end_date, self.cluster_id
        )

        self.assertEqual(len(vol_usage_query.keys()), len(expected_usage_reports.keys()))
        self.assertEqual(len(vol_request_query.keys()), len(expected_request_reports.keys()))

        # Verify that no line items are returned for an incorrect cluster_id
        wrong_cluster_id = self.cluster_id + "bad"
        vol_usage_query = self.accessor.get_persistentvolumeclaim_usage_gigabyte_months(
            start_date, end_date, wrong_cluster_id
        )
        self.assertEqual(len(vol_usage_query.keys()), 0)
        vol_request_query = self.accessor.get_volume_request_storage_gigabyte_months(
            start_date, end_date, wrong_cluster_id
        )
        self.assertEqual(len(vol_request_query.keys()), 0)

    def test_get_volume_gigabyte_months_no_cluster_id(self):
        """Test that gets pod volume usage/request without cluster id."""
        start_date, end_date = self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        # Verify that the line items for the test cluster_id are returned
        reports = (
            self.accessor._get_db_obj_query(table_name)
            .filter(usage_start__gte=start_date, usage_end__lte=end_date, data_source="Storage")
            .all()
        )

        expected_usage_reports = {entry.uuid: entry.persistentvolumeclaim_usage_gigabyte_months for entry in reports}
        expected_request_reports = {entry.uuid: entry.volume_request_storage_gigabyte_months for entry in reports}
        vol_usage_query = self.accessor.get_persistentvolumeclaim_usage_gigabyte_months(start_date, end_date)
        vol_request_query = self.accessor.get_volume_request_storage_gigabyte_months(start_date, end_date)

        self.assertEqual(len(vol_usage_query.keys()), len(expected_usage_reports.keys()))
        self.assertEqual(len(vol_request_query.keys()), len(expected_request_reports.keys()))

    def test_get_daily_usage_query_for_clusterid(self):
        """Test that daily usage getter is correct."""
        self._populate_pod_summary()
        daily_usage = self.accessor.get_daily_usage_query_for_clusterid(self.cluster_id)
        self.assertEqual(daily_usage.count(), 26)

    def test_get_summary_usage_query_for_clusterid(self):
        """Test that daily usage summary getter is correct."""
        daily_usage_summary = self.accessor.get_summary_usage_query_for_clusterid(self.cluster_id)
        with schema_context(self.schema):
            self.assertEqual(daily_usage_summary.count(), 0)
        self._populate_pod_summary()
        with schema_context(self.schema):
            self.assertEqual(daily_usage_summary.count(), 26)

    def test_get_storage_item_query_report_period_id(self):
        """Test that get_storage_item_query_report_period_id is correct."""
        storage_line_item = self.accessor.get_storage_item_query_report_period_id(self.reporting_period.id)
        with schema_context(self.schema):
            self.assertEqual(storage_line_item.count(), 1)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEqual(storage_line_item.count(), 26)

    def test_get_daily_storage_item_query_cluster_id(self):
        """Test that get_daily_storage_item_query_cluster_id is correct."""
        with schema_context(self.schema):
            storage_line_item = self.accessor.get_daily_storage_item_query_cluster_id(self.cluster_id)
            self.assertEqual(storage_line_item.count(), 0)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEqual(storage_line_item.count(), 26)

    def test_get_storage_summary_query_cluster_id(self):
        """Test that get_storage_summary_query_cluster_id is correct."""
        storage_summary = self.accessor.get_storage_summary_query_cluster_id(self.cluster_id)
        with schema_context(self.schema):
            self.assertEqual(storage_summary.count(), 0)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEqual(storage_summary.count(), 26)

    def test_get_report_periods(self):
        """Test that report_periods getter is correct."""
        with schema_context(self.schema):
            periods = self.accessor.get_report_periods()
            self.assertEqual(len(periods), OCPUsageReportPeriod.objects.count())

    def test_get_reports(self):
        """Test that the report getter is correct."""
        with schema_context(self.schema):
            reports = self.accessor.get_reports()
            self.assertEqual(len(reports), OCPUsageReport.objects.count())

    def test_populate_monthly_cost_node_infrastructure_cost(self):
        """Test that the monthly infrastructure cost row for nodes in the summary table is populated."""
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        first_month, _ = month_date_range_tuple(start_date)

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                self.cluster_id = self.ocpaws_ocp_cluster_id
                node_rate = random.randrange(1, 100)
                self.accessor.populate_monthly_cost(
                    "Node",
                    "Infrastructure",
                    node_rate,
                    start_date,
                    end_date,
                    self.cluster_id,
                    self.cluster_id,
                    distribution,
                    self.ocpaws_provider_uuid,
                )
                monthly_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(
                        usage_start=first_month,
                        infrastructure_monthly_cost_json__isnull=False,
                        cluster_id=self.cluster_id,
                    )
                    .all()
                )
                monthly_project_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(
                        usage_start=first_month,
                        infrastructure_project_monthly_cost__isnull=False,
                        cluster_id=self.cluster_id,
                    )
                    .all()
                )
                with schema_context(self.schema):
                    # Test infrastructure monthly node distrbution
                    expected_count = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            report_period__provider_id=self.ocpaws_provider_uuid,
                            usage_start__gte=start_date,
                            infrastructure_monthly_cost_json__isnull=False,
                        )
                        .values("node")
                        .distinct()
                        .count()
                    )
                    self.assertEqual(monthly_cost_rows.count(), expected_count)
                    for monthly_cost_row in monthly_cost_rows:
                        self.assertEqual(
                            monthly_cost_row.infrastructure_monthly_cost_json.get(distribution), node_rate
                        )

                    # Test infrastructure node to project distribution
                    expected_project_value = expected_count * node_rate
                    expected_project_count = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            report_period__provider_id=self.ocpaws_provider_uuid,
                            usage_start__gte=start_date,
                            infrastructure_project_monthly_cost__isnull=False,
                        )
                        .values("node", "namespace")
                        .distinct()
                        .count()
                    )
                    self.assertAlmostEqual(monthly_project_cost_rows.count(), expected_project_count, 6)
                    monthly_project_cost = []
                    for monthly_project_cost_row in monthly_project_cost_rows:
                        monthly_project_cost.append(
                            monthly_project_cost_row.infrastructure_project_monthly_cost.get(distribution)
                        )
                    self.assertAlmostEqual(sum(monthly_project_cost), expected_project_value, 6)

    def test_populate_monthly_cost_node_supplementary_cost(self):
        """Test that the monthly supplementary cost row for nodes in the summary table is populated."""
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        first_month, _ = month_date_range_tuple(start_date)
        cluster_alias = "test_cluster_alias"

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")
                node_rate = random.randrange(1, 100)
                self.accessor.populate_monthly_cost(
                    "Node",
                    "Supplementary",
                    node_rate,
                    start_date,
                    end_date,
                    self.cluster_id,
                    cluster_alias,
                    distribution,
                    self.provider_uuid,
                )
                monthly_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(usage_start=first_month, supplementary_monthly_cost_json__isnull=False)
                    .all()
                )
                monthly_project_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(usage_start=first_month, supplementary_project_monthly_cost__isnull=False)
                    .all()
                )
                with schema_context(self.schema):
                    # Test supplementary monthly node distrbution
                    expected_count = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            report_period__provider_id=self.ocp_provider.uuid,
                            usage_start__gte=start_date,
                            supplementary_monthly_cost_json__isnull=False,
                        )
                        .values("node")
                        .distinct()
                        .count()
                    )
                    self.assertEqual(monthly_cost_rows.count(), expected_count)
                    for monthly_cost_row in monthly_cost_rows:
                        self.assertEqual(monthly_cost_row.supplementary_monthly_cost_json.get(distribution), node_rate)

                    # Test supplementary node to project distribution
                    expected_project_value = expected_count * node_rate
                    expected_project_count = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            report_period__provider_id=self.ocp_provider.uuid,
                            usage_start__gte=start_date,
                            supplementary_project_monthly_cost__isnull=False,
                        )
                        .values("node", "namespace")
                        .distinct()
                        .count()
                    )
                    self.assertEqual(monthly_project_cost_rows.count(), expected_project_count)
                    monthly_project_cost = []
                    for monthly_project_cost_row in monthly_project_cost_rows:
                        monthly_project_cost.append(
                            monthly_project_cost_row.supplementary_project_monthly_cost.get(distribution)
                        )
                    self.assertAlmostEqual(sum(monthly_project_cost), expected_project_value, 6)

    def test_populate_monthly_cost_cluster_infrastructure_cost(self):
        """Test that the monthly infrastructure cost row for clusters in the summary table is populated."""
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        dh = DateHelper()
        start_date = dh.last_month_start
        end_date = dh.this_month_start
        first_month, _ = month_date_range_tuple(start_date)
        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                self.cluster_id = self.ocp_cluster_id
                cluster_rate = random.randrange(1, 100)
                self.accessor.populate_monthly_cost(
                    "Cluster",
                    "Infrastructure",
                    cluster_rate,
                    start_date,
                    end_date,
                    self.cluster_id,
                    self.cluster_id,
                    distribution,
                    self.provider_uuid,
                )

                monthly_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(usage_start=first_month, infrastructure_monthly_cost_json__isnull=False)
                    .all()
                )

                project_monthly_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(usage_start=first_month, infrastructure_project_monthly_cost__isnull=False)
                    .all()
                )

                with schema_context(self.schema):
                    # Test cluster to node distribution
                    sum_row_list = []
                    for monthly_cost_row in monthly_cost_rows:
                        sum_row_list.append(monthly_cost_row.infrastructure_monthly_cost_json.get(distribution))
                    #  handle small possible imprecision due to division
                    # eg. 56.99999999999999 != 57
                    self.assertLessEqual((cluster_rate - sum(sum_row_list)), 0.001)

                    # Test cluster to project distribution
                    project_sum_list = []
                    for p_monthly_cost_row in project_monthly_cost_rows:
                        project_sum_list.append(
                            p_monthly_cost_row.infrastructure_project_monthly_cost.get(distribution)
                        )
                    self.assertLessEqual((cluster_rate - sum(project_sum_list)), 0.001)

    def test_populate_monthly_cost_cluster_supplementary_cost(self):
        """Test that the monthly infrastructure cost row for clusters in the summary table is populated."""
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        dh = DateHelper()
        start_date = dh.last_month_start
        end_date = dh.this_month_start
        first_month, _ = month_date_range_tuple(start_date)

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                self.cluster_id = self.ocp_cluster_id
                cluster_rate = random.randrange(1, 100)
                self.accessor.populate_monthly_cost(
                    "Cluster",
                    "Supplementary",
                    cluster_rate,
                    start_date,
                    end_date,
                    self.cluster_id,
                    self.cluster_id,  # the alias is the same as id in bakery at the moment
                    distribution,
                    self.provider_uuid,
                )

                monthly_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(usage_start=first_month, supplementary_monthly_cost_json__isnull=False)
                    .all()
                )

                project_monthly_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(usage_start=first_month, supplementary_project_monthly_cost__isnull=False)
                    .all()
                )
                with schema_context(self.schema):
                    # Test cluster to node distribution
                    sum_row_list = []
                    for monthly_cost_row in monthly_cost_rows:
                        sum_row_list.append(monthly_cost_row.supplementary_monthly_cost_json.get(distribution))
                    self.assertLessEqual((cluster_rate - sum(sum_row_list)), 0.001)

                    # Test cluster to project distribution
                    project_sum_list = []
                    for p_monthly_cost_row in project_monthly_cost_rows:
                        project_sum_list.append(
                            p_monthly_cost_row.supplementary_project_monthly_cost.get(distribution)
                        )
                    self.assertLessEqual((cluster_rate - sum(project_sum_list)), 0.001)

    def test_populate_monthly_cost_pvc_infrastructure_cost(self):
        """Test that the monthly infrastructure cost row for PVC in the summary table is populated."""
        self.cluster_id = self.ocpaws_ocp_cluster_id

        pvc_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, _ = month_date_range_tuple(start_date)

        self.accessor.populate_monthly_cost(
            "PVC",
            "Infrastructure",
            pvc_rate,
            start_date,
            end_date,
            self.cluster_id,
            self.cluster_id,
            metric_constants.CPU_DISTRIBUTION,
            self.ocpaws_provider_uuid,
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(
                cluster_id=self.cluster_id, usage_start=first_month, infrastructure_monthly_cost_json__isnull=False
            )
            .all()
        )

        project_monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(
                cluster_id=self.cluster_id, usage_start=first_month, infrastructure_project_monthly_cost__isnull=False
            )
            .all()
        )

        with schema_context(self.schema):
            # Test unique (pvc, node, namespace) distribution
            expected_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    report_period__provider_id=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    persistentvolumeclaim__isnull=False,
                )
                .values("persistentvolumeclaim", "node", "namespace")
                .distinct()
                .count()
            )
            self.assertEqual(monthly_cost_rows.count(), expected_count)
            for monthly_cost_row in monthly_cost_rows:
                self.assertEqual(
                    monthly_cost_row.infrastructure_monthly_cost_json.get(metric_constants.PVC_DISTRIBUTION), pvc_rate
                )
            # Test pvc to project distribution
            expected_project_total = expected_count * pvc_rate
            expected_project_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    report_period__provider_id=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    persistentvolumeclaim__isnull=False,
                    namespace__isnull=False,
                )
                .values("persistentvolumeclaim", "node", "namespace")
                .distinct()
                .count()
            )
            self.assertEqual(project_monthly_cost_rows.count(), expected_project_count)
            project_total = []
            for p_monthly_cost_row in project_monthly_cost_rows:
                pvc_project_cost = p_monthly_cost_row.infrastructure_project_monthly_cost.get(
                    metric_constants.PVC_DISTRIBUTION
                )
                project_total.append(pvc_project_cost)
                self.assertEqual(pvc_project_cost, pvc_rate)
            self.assertEqual(sum(project_total), expected_project_total)

    def test_populate_monthly_cost_pvc_supplementary_cost(self):
        """Test that the monthly supplementary cost row for PVC in the summary table is populated."""
        cost_type = "PVC"
        self.cluster_id = self.ocp_cluster_id

        pvc_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, _ = month_date_range_tuple(start_date)

        for curr_month in rrule(freq=MONTHLY, until=end_date, dtstart=first_month):
            first_curr_month, first_next_month = month_date_range_tuple(curr_month)
            self.accessor.remove_monthly_cost(first_curr_month, first_next_month, self.cluster_id, cost_type)
        self.accessor.populate_monthly_cost(
            cost_type,
            "Supplementary",
            pvc_rate,
            start_date,
            end_date,
            self.cluster_id,
            self.cluster_id,
            metric_constants.CPU_DISTRIBUTION,
            self.provider_uuid,
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, supplementary_monthly_cost_json__isnull=False)
            .all()
        )

        project_monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, supplementary_project_monthly_cost__isnull=False)
            .all()
        )

        with schema_context(self.schema):
            # Test pvc to node distribution
            expected_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    report_period__provider_id=self.ocp_provider.uuid,
                    usage_start__gte=start_date,
                    persistentvolumeclaim__isnull=False,
                )
                .values("persistentvolumeclaim", "node", "namespace")
                .distinct()
                .count()
            )
            self.assertEqual(monthly_cost_rows.count(), expected_count)
            for monthly_cost_row in monthly_cost_rows:
                self.assertEqual(
                    monthly_cost_row.supplementary_monthly_cost_json.get(metric_constants.PVC_DISTRIBUTION), pvc_rate
                )

            # Test pvc to project distribution
            expected_project_total = expected_count * pvc_rate
            expected_project_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    report_period__provider_id=self.ocp_provider.uuid,
                    usage_start__gte=start_date,
                    persistentvolumeclaim__isnull=False,
                    namespace__isnull=False,
                )
                .values("persistentvolumeclaim", "node", "namespace")
                .distinct()
                .count()
            )
            self.assertEqual(project_monthly_cost_rows.count(), expected_project_count)
            project_total = []
            for p_monthly_cost_row in project_monthly_cost_rows:
                pvc_project_cost = p_monthly_cost_row.supplementary_project_monthly_cost.get(
                    metric_constants.PVC_DISTRIBUTION
                )
                project_total.append(pvc_project_cost)
                self.assertEqual(pvc_project_cost, pvc_rate)
            self.assertEqual(sum(project_total), expected_project_total)

    def test_remove_monthly_cost(self):
        """Test that the monthly cost row in the summary table is removed."""
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        first_month, first_next_month = month_date_range_tuple(start_date)
        cost_type = "Node"

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")
                node_rate = random.randrange(1, 100)
                rate_type = metric_constants.SUPPLEMENTARY_COST_TYPE
                self.accessor.populate_monthly_cost(
                    cost_type,
                    rate_type,
                    node_rate,
                    start_date,
                    end_date,
                    self.cluster_id,
                    self.cluster_id,
                    distribution,
                    self.provider_uuid,
                )
                monthly_cost_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(usage_start=first_month, supplementary_monthly_cost_json__isnull=False)
                    .all()
                )
                project_monthly_rows = (
                    self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
                    .filter(usage_start=first_month, supplementary_project_monthly_cost__isnull=False)
                    .all()
                )
                with schema_context(self.schema):
                    self.assertTrue(monthly_cost_rows.exists())
                    self.assertTrue(project_monthly_rows.exists())
                self.accessor.remove_monthly_cost(start_date, first_next_month, self.cluster_id, cost_type)
                with schema_context(self.schema):
                    self.assertFalse(monthly_cost_rows.exists())
                    self.assertFalse(project_monthly_rows.exists())

    def test_remove_monthly_cost_no_data(self):
        """Test that an error isn't thrown when the monthly cost row has no data."""
        start_date = DateAccessor().today_with_timezone("UTC")
        end_date = DateAccessor().today_with_timezone("UTC")
        cost_type = "Node"

        try:
            self.accessor.remove_monthly_cost(start_date, end_date, self.cluster_id, cost_type)
        except Exception as err:
            self.fail(f"Exception thrown: {err}")

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.trino_db.executescript")
    @patch("masu.database.ocp_report_db_accessor.trino_db.connect")
    def test_populate_line_item_daily_summary_table_presto(self, mock_connect, mock_executescript, mock_table_exists):
        """
        Test that OCP presto processing calls executescript
        """
        presto_conn = FakePrestoConn()
        mock_table_exists.return_value = True
        mock_connect.return_value = presto_conn
        mock_executescript.return_value = []
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.next_month_start
        cluster_id = "ocp-cluster"
        cluster_alias = "OCP FTW"
        report_period_id = 1
        source = self.provider_uuid
        self.accessor.populate_line_item_daily_summary_table_presto(
            start_date, end_date, report_period_id, cluster_id, cluster_alias, source
        )
        mock_connect.assert_called()
        mock_executescript.assert_called()

    # @patch("masu.util.common.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.pkgutil.get_data")
    @patch("masu.database.ocp_report_db_accessor.trino_db.connect")
    def test_populate_line_item_daily_summary_table_presto_preprocess_exception(
        self, mock_connect, mock_get_data, mock_table_exists
    ):
        """
        Test that OCP presto processing converts datetime to date for start, end dates
        """
        presto_conn = FakePrestoConn()
        mock_table_exists.return_value = True
        mock_connect.return_value = presto_conn
        mock_get_data.return_value = b"""
select * from eek where val1 in {{report_period_id}} ;
"""
        start_date = "2020-01-01"
        end_date = "2020-02-01"
        report_period_id = (1, 2)  # This should generate a preprocessor error
        cluster_id = "ocp-cluster"
        cluster_alias = "OCP FTW"
        source = self.provider_uuid
        with self.assertRaises(trino_db.PreprocessStatementError):
            self.accessor.populate_line_item_daily_summary_table_presto(
                start_date, end_date, report_period_id, cluster_id, cluster_alias, source
            )

    def test_populate_node_label_line_item_daily_table(self):
        """Test that the node label line item daily table populates."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        daily_table_name = OCP_REPORT_TABLE_MAP["node_label_line_item_daily"]

        report_table = getattr(self.accessor.report_schema, report_table_name)
        daily_table = getattr(self.accessor.report_schema, daily_table_name)

        for _ in range(5):
            self.creator.create_ocp_node_label_line_item(self.reporting_period, self.report)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(daily_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_node_label_line_item_daily_table(start_date, end_date, self.cluster_id)

        self.assertNotEqual(query.count(), initial_count)

        with schema_context(self.schema):
            daily_entry = daily_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = daily_entry["usage_start__min"]
            result_end_date = daily_entry["usage_start__max"]

        self.assertEqual(result_start_date, start_date.date())
        self.assertEqual(result_end_date, end_date.date())

        with schema_context(self.schema):
            entry = query.first()

            summary_columns = ["cluster_id", "node", "node_labels", "total_seconds", "usage_end", "usage_start"]

            for column in summary_columns:
                self.assertIsNotNone(getattr(entry, column))

    def test_upsert_monthly_cluster_cost_line_item_no_report_period(self):
        """Test that the cluster monthly costs are not updated when no report period  is found."""
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        report_table = getattr(self.accessor.report_schema, report_table_name)
        rate = 1000
        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
                    start_date = report_entry["interval_start__min"].replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = report_entry["interval_start__max"].replace(hour=0, minute=0, second=0, microsecond=0)
                    self.accessor.upsert_monthly_cluster_cost_line_item(
                        start_date,
                        end_date,
                        self.cluster_id,
                        "cluster_alias",
                        metric_constants.SUPPLEMENTARY_COST_TYPE,
                        rate,
                        distribution,
                        self.provider_uuid,
                        {},  # cost_category_mapping
                    )
                    summary_table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
                    query = self.accessor._get_db_obj_query(summary_table_name)
                    self.assertFalse(query.filter(cluster_id=self.cluster_id).exists())

    # tag based testing is below
    def test_populate_monthly_tag_cost_node_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for nodes in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            nodes = self.accessor.get_distinct_nodes(start_date, end_date, self.cluster_id)
            # The number of unique pod_labels key value pairs per node
            k_v_pairs = (
                OCPUsageLineItemDailySummary.objects.filter(**{"pod_labels__has_key": tag_rate_key})
                .distinct()
                .values_list("pod_labels", "node")
                .filter(
                    cluster_id=self.cluster_id,
                    source_uuid=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    usage_end__lte=end_date,
                    node__in=nodes,
                )
            )
            key_value_pairs = {tag_rate_key: [tag_node[0].get(tag_rate_key) for tag_node in k_v_pairs]}
        node_tag_rates = {}
        node_rate = random.randrange(1, 100)
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                values_dict[value] = node_rate
            node_tag_rates[key] = values_dict

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Node",
                    )
                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_cost(
                        "Node",
                        "Infrastructure",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )

                    # assert that after the update, there are now the monthly values
                    # for the three different nodes that have a value
                    self.assertEqual(qset.count(), len(nodes))
                    qset_total = 0
                    for value in qset:
                        qset_total += value.infrastructure_monthly_cost_json.get(distribution, 0)
                    expected_total = len(k_v_pairs) * node_rate
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_default_tag_cost_node_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for nodes in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        default_val = random.randrange(10, 100)
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            tag_rate_vals = (
                OCPUsageLineItemDailySummary.objects.filter(pod_labels__has_key=tag_rate_key)
                .distinct()
                .values_list("pod_labels", flat=True)
            )[1]
            nodes = self.accessor.get_distinct_nodes(start_date, end_date, self.cluster_id)
            # The number of unique pod_labels key value pairs per node
            k_v_pairs_num = (
                OCPUsageLineItemDailySummary.objects.filter(
                    pod_labels__has_key=tag_rate_key,
                    cluster_id=self.cluster_id,
                    source_uuid=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    usage_end__lte=end_date,
                    node__in=nodes,
                )
                .values_list("pod_labels", "node")
                .distinct()
                .count()
            )

        node_tag_rates = {tag_rate_key: {"default_value": default_val, "defined_keys": tag_rate_vals}}

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    _ = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            infrastructure_monthly_cost_json__isnull=False,
                            monthly_cost_type="Node",
                        )
                    ).delete()

                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Node",
                    )

                    # call populate monthly default tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_default_cost(
                        "Node",
                        "Infrastructure",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )

                    # assert that after the update, there are now the monthly values
                    # for the two different nodes that did not have a value defined
                    self.assertEqual(qset.count(), len(nodes))
                    qset_total = 0
                    for value in qset:
                        qset_total += value.infrastructure_monthly_cost_json.get(distribution, 0)
                    # replicates the node matches
                    expected_total = k_v_pairs_num * default_val
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_default_tag_cost_node_supplementary_cost(self):
        """
        Test that the monthly infrastructure cost row for nodes in the summary table
        is populated when given tag based rates.
        """
        self.cluster_id = self.ocpaws_ocp_cluster_id
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        default_val = random.randrange(10, 100)

        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            tag_rate_vals = (
                OCPUsageLineItemDailySummary.objects.filter(pod_labels__has_key=tag_rate_key)
                .distinct()
                .values_list("pod_labels", flat=True)
            )[1]
            nodes = self.accessor.get_distinct_nodes(start_date, end_date, self.cluster_id)
            # The number of unique pod_labels key value pairs per node
            k_v_pairs_num = (
                OCPUsageLineItemDailySummary.objects.filter(
                    pod_labels__has_key=tag_rate_key,
                    cluster_id=self.cluster_id,
                    source_uuid=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    usage_end__lte=end_date,
                    node__in=nodes,
                )
                .values_list("pod_labels", "node")
                .distinct()
                .count()
            )

        node_tag_rates = {tag_rate_key: {"default_value": default_val, "defined_keys": tag_rate_vals}}

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        supplementary_monthly_cost_json__isnull=False,
                        monthly_cost_type="Node",
                    )

                    OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Node",
                    ).delete()
                    self.accessor.populate_monthly_tag_default_cost(
                        "Node",
                        "Supplementary",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )

                    # for the two different nodes that did not have a value defined
                    self.assertEqual(qset.count(), len(nodes))
                    # replicates the node matches
                    expected_total = k_v_pairs_num * default_val
                    qset_total = 0
                    for value in qset:
                        qset_total += value.supplementary_monthly_cost_json.get(distribution, 0)
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_tag_cost_pvc_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for PVCs in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            pvcs = self.accessor.get_distinct_pvcs(start_date, end_date, self.cluster_id)

            k_v_pairs = (
                OCPUsageLineItemDailySummary.objects.filter(
                    cluster_id=self.cluster_id,
                    source_uuid=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    usage_end__lte=end_date,
                    volume_labels__has_key=tag_rate_key,
                )
                .distinct()
                .values_list("volume_labels", "node")
            )
            key_value_pairs = {tag_rate_key: list({tag_node[0].get(tag_rate_key) for tag_node in k_v_pairs})}

        pvc_tag_rates = {}
        pvc_rate = random.randrange(1, 100)
        for key, values in key_value_pairs.items():
            pvc_tag_rates[key] = {value: pvc_rate for value in values}

        with schema_context(self.schema):
            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, infrastructure_monthly_cost_json__isnull=False, monthly_cost_type="PVC"
            )
            # assert that there are no infrastructure monthly PVC costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "PVC",
                "Infrastructure",
                pvc_tag_rates,
                start_date,
                end_date,
                self.cluster_id,
                self.cluster_id,
                metric_constants.CPU_DISTRIBUTION,
                self.ocpaws_provider_uuid,
            )

            self.assertEqual(qset.count(), len(pvcs))
            qset_total = sum(
                value.infrastructure_monthly_cost_json.get(metric_constants.PVC_DISTRIBUTION, 0) for value in qset
            )

            expected_total = len(k_v_pairs) * pvc_rate
            self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_tag_cost_node_supplementary_cost(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            nodes = self.accessor.get_distinct_nodes(start_date, end_date, self.cluster_id)
            # The number of unique pod_labels key value pairs per node
            k_v_pairs = (
                OCPUsageLineItemDailySummary.objects.filter(**{"pod_labels__has_key": tag_rate_key})
                .distinct()
                .values_list("pod_labels", "node")
                .filter(
                    cluster_id=self.cluster_id,
                    source_uuid=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    usage_end__lte=end_date,
                    node__in=nodes,
                )
            )
            key_value_pairs = {tag_rate_key: [tag_node[0].get(tag_rate_key) for tag_node in k_v_pairs]}
        node_tag_rates = {}
        rate_total = 0
        node_rate = random.randrange(1, 100)
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                values_dict[value] = node_rate
                rate_total += node_rate
            node_tag_rates[key] = values_dict

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    # create a query set based on the criteria we are looking for
                    # so it can be evaluated before and after the function call
                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        supplementary_monthly_cost_json__isnull=False,
                        monthly_cost_type="Node",
                    )
                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_cost(
                        "Node",
                        "Supplementary",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )
                    # assert that after the update, there are now the monthly values for
                    # the three different nodes that have a value
                    self.assertEqual(qset.count(), len(nodes))
                    qset_total = 0
                    for value in qset:
                        qset_total += value.supplementary_monthly_cost_json.get(distribution, 0)
                    expected_total = node_rate * len(k_v_pairs)
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_tag_cost_pvc_supplementary_cost(self):
        """
        Test that the monthly supplementary cost row for PVCs in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            pvcs = self.accessor.get_distinct_pvcs(start_date, end_date, self.cluster_id)

            k_v_pairs = (
                OCPUsageLineItemDailySummary.objects.filter(
                    cluster_id=self.cluster_id,
                    source_uuid=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    usage_end__lte=end_date,
                    volume_labels__has_key=tag_rate_key,
                )
                .distinct()
                .values_list("volume_labels", "node")
            )
            key_value_pairs = {tag_rate_key: list({tag_node[0].get(tag_rate_key) for tag_node in k_v_pairs})}

        pvc_tag_rates = {}
        pvc_rate = random.randrange(1, 100)
        for key, values in key_value_pairs.items():
            pvc_tag_rates[key] = {value: pvc_rate for value in values}
        with schema_context(self.schema):
            # create a query set based on the criteria we are looking for
            # so it can be evaluated before and after the function call
            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, supplementary_monthly_cost_json__isnull=False, monthly_cost_type="PVC"
            )
            # assert that there are no infrastructure monthly PVC costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "PVC",
                "Supplementary",
                pvc_tag_rates,
                start_date,
                end_date,
                self.cluster_id,
                self.cluster_id,
                metric_constants.CPU_DISTRIBUTION,
                self.ocpaws_provider_uuid,
            )

            self.assertEqual(qset.count(), len(pvcs))
            qset_total = 0
            for value in qset:
                qset_total += value.supplementary_monthly_cost_json.get(metric_constants.PVC_DISTRIBUTION, 0)
            expected_total = len(k_v_pairs) * pvc_rate
            self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_default_tag_cost_pvc_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for PVCs in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        default_val = random.randrange(1, 100)
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            tag_rate_vals = (
                OCPUsageLineItemDailySummary.objects.filter(pod_labels__has_key=tag_rate_key)
                .distinct()
                .values_list("pod_labels", flat=True)
            )[1]
            pvcs = self.accessor.get_distinct_pvcs(start_date, end_date, self.cluster_id)
            # The number of unique pod_labels key value pairs per node
            k_v_pairs_num = (
                OCPUsageLineItemDailySummary.objects.filter(
                    pod_labels__has_key=tag_rate_key,
                    cluster_id=self.cluster_id,
                    source_uuid=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    usage_end__lte=end_date,
                )
                .values_list("pod_labels", "node")
                .distinct()
                .count()
            )

        node_tag_rates = {tag_rate_key: {"default_value": default_val, "defined_keys": tag_rate_vals}}

        with schema_context(self.schema):
            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, infrastructure_monthly_cost_json__isnull=False, monthly_cost_type="PVC"
            )
            # assert that there are no infrastructure monthly PVC costs currently on our cluster id
            self.assertEqual(qset.count(), 0)

            # call populate monthly default tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_default_cost(
                "PVC",
                "Infrastructure",
                node_tag_rates,
                start_date,
                end_date,
                self.cluster_id,
                self.cluster_id,
                metric_constants.CPU_DISTRIBUTION,
                self.ocpaws_provider_uuid,
            )

            # assert that after the update, there is now the cluster cost for the PVC
            self.assertEqual(qset.count(), len(pvcs))
            qset_total = 0
            for value in qset:
                qset_total += value.infrastructure_monthly_cost_json.get(metric_constants.PVC_DISTRIBUTION)
            # there are three PVC tags and we said two already have defined rates
            expected_total = default_val * k_v_pairs_num
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_default_tag_cost_pvc_supplementary_cost(self):
        """
        Test that the monthly infrastructure cost row for PVC's in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        default_val = random.randrange(1, 100)
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            tag_rate_vals = (
                OCPUsageLineItemDailySummary.objects.filter(**{"pod_labels__has_key": tag_rate_key})
                .distinct()
                .values_list("pod_labels", flat=True)
            )[1]
            pvcs = self.accessor.get_distinct_pvcs(start_date, end_date, self.cluster_id)
            # The number of unique pod_labels key value pairs per node
            k_v_pairs_num = (
                OCPUsageLineItemDailySummary.objects.filter(
                    pod_labels__has_key=tag_rate_key,
                    cluster_id=self.cluster_id,
                    source_uuid=self.ocpaws_provider_uuid,
                    usage_start__gte=start_date,
                    usage_end__lte=end_date,
                )
                .values_list("pod_labels", "node")
                .distinct()
                .count()
            )

        node_tag_rates = {tag_rate_key: {"default_value": default_val, "defined_keys": tag_rate_vals}}
        with schema_context(self.schema):
            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, supplementary_monthly_cost_json__isnull=False, monthly_cost_type="PVC"
            )

            # assert that there are no supplementary monthly PVC costs currently on our cluster id
            self.assertEqual(qset.count(), 0)

            # call populate monthly default tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_default_cost(
                "PVC",
                "Supplementary",
                node_tag_rates,
                start_date,
                end_date,
                self.cluster_id,
                self.cluster_id,
                metric_constants.CPU_DISTRIBUTION,
                self.ocpaws_provider_uuid,
            )

            # assert that after the update, there are now the monthly values
            # for the PVC's
            self.assertEqual(qset.count(), len(pvcs))
            qset_total = 0
            for value in qset:
                qset_total += value.supplementary_monthly_cost_json.get(metric_constants.PVC_DISTRIBUTION)
            expected_total = default_val * k_v_pairs_num
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_tag_cost_node_no_rates(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is not populated when given no tag rates.
        """
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        node_tag_rates = {}
        rate_total = 0
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                self.cluster_id = "OCP-on-Azure"
                with schema_context(self.schema):
                    # grab one item with the pod_labels we are looking for so the cluster_alias can be gotten
                    k_v = (
                        OCPUsageLineItemDailySummary.objects.filter(pod_labels__contains={"app": "banking"})
                        .values()
                        .first()
                    )
                    c_a = k_v.get("cluster_alias")

                    # create a query set based on the criteria we are looking for
                    # so it can be evaluated before and after the function call
                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        supplementary_monthly_cost_json__isnull=False,
                        monthly_cost_type="Node",
                    )
                    # assert that there are no infrastructure monthly node costs currently on our cluster id
                    self.assertEqual(qset.count(), 0)
                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_cost(
                        "Node",
                        "Supplementary",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        c_a,
                        distribution,
                        self.provider_uuid,
                    )
                    # assert that after the update, there are still no monthly costs for nodes in supplementary
                    self.assertEqual(qset.count(), 0)
                    qset_total = 0
                    for value in qset:
                        qset_total += value.supplementary_monthly_cost_json.get(distribution, 0)
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_pvc_no_rates(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is not populated when given no tag rates.
        """
        node_tag_rates = {}
        rate_total = 0

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-Azure"
        with schema_context(self.schema):
            # grab one item with the pod_labels we are looking for so the cluster_alias can be gotten
            k_v = OCPUsageLineItemDailySummary.objects.filter(pod_labels__contains={"app": "banking"}).values().first()
            c_a = k_v.get("cluster_alias")

            # create a query set based on the criteria we are looking for
            # so it can be evaluated before and after the function call
            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, supplementary_monthly_cost_json__isnull=False, monthly_cost_type="PVC"
            )
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "PVC",
                "Supplementary",
                node_tag_rates,
                start_date,
                end_date,
                self.cluster_id,
                c_a,
                metric_constants.CPU_DISTRIBUTION,
                self.provider_uuid,
            )
            # assert that after the update, there are still no monthly costs for nodes in supplementary
            self.assertEqual(qset.count(), 0)
            qset_total = 0
            for value in qset:
                qset_total += value.supplementary_monthly_cost_json.get(metric_constants.PVC_DISTRIBUTION)
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_node_bad_key_value_pairs(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is not populated when the key_value pairs do not match.
        """
        key_value_pairs = {"word": ["pickle", "fridge", "waterfall"]}
        node_tag_rates = {}
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
            node_tag_rates[key] = values_dict

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-Azure"
        with schema_context(self.schema):
            # grab one item with the pod_labels we are looking for so the cluster_alias can be gotten
            k_v = OCPUsageLineItemDailySummary.objects.filter(pod_labels__contains={"app": "banking"}).values().first()
            c_a = k_v.get("cluster_alias")

            # create a query set based on the criteria we are looking for
            # so it can be evaluated before and after the function call
            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, supplementary_monthly_cost_json__isnull=False, monthly_cost_type="Node"
            )
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Node",
                "Supplementary",
                node_tag_rates,
                start_date,
                end_date,
                self.cluster_id,
                c_a,
                metric_constants.CPU_DISTRIBUTION,
                self.provider_uuid,
            )
            # assert that after the update, there are still no node costs since the key_value pairs did not match
            self.assertEqual(qset.count(), 0)

    def test_populate_monthly_tag_cost_cluster_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for cluster in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            k_v_pairs = (
                OCPUsageLineItemDailySummary.objects.filter(
                    **{
                        "pod_labels__has_key": tag_rate_key,
                        "usage_start__gte": start_date,
                        "usage_start__lte": end_date,
                    }
                )
                .distinct()
                .values_list("pod_labels", flat=True)
                .filter(cluster_id=self.cluster_id)
            )
            key_value_pairs = {tag_rate_key: [dikt[tag_rate_key] for dikt in k_v_pairs]}
        rate_total = 0
        node_tag_rates = {}
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
                rate_total += node_rate
            node_tag_rates[key] = values_dict
        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    # create a query set based on the criteria we are looking for
                    # so it can be evaluated before and after the function call
                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    )
                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_cost(
                        "Cluster",
                        "Infrastructure",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )
                    # assert that after the update, there is now the value for the cluster we specified
                    self.assertEqual(qset.count(), 1)
                    qset_total = 0
                    for value in qset:
                        qset_total += value.infrastructure_monthly_cost_json.get(distribution, 0)
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_cluster_supplementary_cost(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is populated when given tag based rates.
        """
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            k_v_pairs = (
                OCPUsageLineItemDailySummary.objects.filter(
                    **{
                        "pod_labels__has_key": tag_rate_key,
                        "usage_start__gte": start_date,
                        "usage_start__lte": end_date,
                    }
                )
                .distinct()
                .values_list("pod_labels", flat=True)
                .filter(cluster_id=self.cluster_id)
            )
            key_value_pairs = {tag_rate_key: [dikt[tag_rate_key] for dikt in k_v_pairs]}
        rate_total = 0
        node_tag_rates = {}
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
                rate_total += node_rate
            node_tag_rates[key] = values_dict

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    # create a query set based on the criteria we are looking for
                    # so it can be evaluated before and after the function call
                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        supplementary_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    )
                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_cost(
                        "Cluster",
                        "Supplementary",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )
                    # assert that after the update, there is now the value for the cluster we specified
                    self.assertEqual(qset.count(), 1)
                    qset_total = 0
                    for value in qset:
                        qset_total += value.supplementary_monthly_cost_json.get(distribution, 0)
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_cluster_supplementary_cost_string_dates(self):
        """
        Test that when strings are given as dates, it handles it correctly
        """
        dh = DateHelper()
        start_date = dh.this_month_start.strftime("%Y-%m-%d")
        end_date = dh.this_month_end.strftime("%Y-%m-%d")
        self.cluster_id = self.ocpaws_ocp_cluster_id
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            k_v_pairs = (
                OCPUsageLineItemDailySummary.objects.filter(
                    **{
                        "pod_labels__has_key": tag_rate_key,
                        "usage_start__gte": start_date,
                        "usage_start__lte": end_date,
                    }
                )
                .distinct()
                .values_list("pod_labels", flat=True)
                .filter(cluster_id=self.cluster_id)
            )
            key_value_pairs = {tag_rate_key: [dikt[tag_rate_key] for dikt in k_v_pairs]}
        node_tag_rates = {}
        rate_total = 0
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
                rate_total += node_rate
            node_tag_rates[key] = values_dict

        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    _ = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            infrastructure_monthly_cost_json__isnull=False,
                            monthly_cost_type="Cluster",
                        )
                    ).delete()

                    # create a query set based on the criteria we are looking for
                    # so it can be evaluated before and after the function call
                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        supplementary_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    )
                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_cost(
                        "Cluster",
                        "Supplementary",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )
                    # assert that after the update, there is now the value for the cluster we specified
                    self.assertEqual(qset.count(), 1)
                    qset_total = 0
                    for value in qset:
                        qset_total += value.supplementary_monthly_cost_json.get(distribution, 0)
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_default_tag_cost_cluster_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for a cluster in the summary table
        is populated when given tag based rates.
        """
        self.cluster_id = self.ocpaws_ocp_cluster_id
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            tag_rate_vals = (
                OCPUsageLineItemDailySummary.objects.filter(pod_labels__has_key=tag_rate_key)
                .distinct()
                .values_list("pod_labels", flat=True)
            )[1]

        default_val = random.randrange(1, 100)
        for distribution in distribution_choices:
            with self.subTest(distribution=distribution, default_val=default_val):
                node_tag_rates = {tag_rate_key: {"default_value": default_val, "defined_keys": [tag_rate_vals]}}
                with schema_context(self.schema):
                    k_v_pairs_num = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            pod_labels__has_key=tag_rate_key,
                            usage_start__gte=start_date,
                            usage_start__lte=end_date,
                            cluster_id=self.cluster_id,
                        )
                        .values_list("pod_labels", flat=True)
                        .distinct()
                        .count()
                    )

                    OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    ).delete()
                    self.accessor.populate_monthly_tag_default_cost(
                        "Cluster",
                        "Infrastructure",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )

                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                        source_uuid=self.ocpaws_provider_uuid,
                        data_source="Pod",
                    )

                    self.assertEqual(len(qset), 1)
                    qset_total = sum(value.infrastructure_monthly_cost_json.get(distribution, 0) for value in qset)

                    expected_total = default_val * k_v_pairs_num
                    self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_default_tag_cost_cluster_infrastructure_cost_string_dates(self):
        """
        Test that the monthly infrastructure cost row for a cluster in the summary table
        is populated when given tag based rates.
        """
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        default_val = random.randrange(1, 100)
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            tag_rate_vals = (
                OCPUsageLineItemDailySummary.objects.filter(**{"pod_labels__has_key": tag_rate_key})
                .distinct()
                .values_list("pod_labels", flat=True)
            )[1]
        node_tag_rates = {tag_rate_key: {"default_value": default_val, "defined_keys": tag_rate_vals}}
        dh = DateHelper()
        start_date = dh.this_month_start.strftime("%Y-%m-%d")
        end_date = dh.this_month_end.strftime("%Y-%m-%d")
        self.cluster_id = self.ocpaws_ocp_cluster_id
        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    ).delete()
                    k_v_pairs_num = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            pod_labels__has_key=tag_rate_key,
                            usage_start__gte=start_date,
                            usage_start__lte=end_date,
                            cluster_id=self.cluster_id,
                        )
                        .values_list("pod_labels")
                        .distinct()
                        .count()
                    )

                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    )

                    # call populate monthly default tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_default_cost(
                        "Cluster",
                        "Infrastructure",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )

                    self.assertEqual(qset.count(), 1)
                    qset_total = 0
                    for value in qset:
                        qset_total += value.infrastructure_monthly_cost_json.get(distribution, 0)
                    expected_total = default_val * k_v_pairs_num
                    self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_default_tag_cost_cluster_supplementary_cost(self):
        """
        Test that the monthly infrastructure cost row for a cluster in the summary table
        is populated when given tag based rates.
        """
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        default_val = random.randrange(1, 100)
        with schema_context(self.schema):
            tag_rate_key = OCPEnabledTagKeys.objects.distinct("key").values_list("key", flat=True)[0]
            tag_rate_vals = (
                OCPUsageLineItemDailySummary.objects.filter(pod_labels__has_key=tag_rate_key)
                .distinct()
                .values_list("pod_labels", flat=True)
            )[1]
        node_tag_rates = {tag_rate_key: {"default_value": default_val, "defined_keys": tag_rate_vals}}
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = self.ocpaws_ocp_cluster_id
        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                with schema_context(self.schema):
                    OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        infrastructure_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    ).delete()
                    k_v_pairs_num = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            pod_labels__has_key=tag_rate_key,
                            usage_start__gte=start_date,
                            usage_start__lte=end_date,
                            cluster_id=self.cluster_id,
                        )
                        .values_list("pod_labels")
                        .distinct()
                        .count()
                    )

                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        supplementary_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    )

                    # call populate monthly default tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_default_cost(
                        "Cluster",
                        "Supplementary",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        self.cluster_id,
                        distribution,
                        self.ocpaws_provider_uuid,
                    )

                    # assert that after the update, there are now the monthly values
                    # for the cluster
                    self.assertEqual(qset.count(), 1)
                    qset_total = 0
                    for value in qset:
                        qset_total += value.supplementary_monthly_cost_json.get(distribution, 0)
                    expected_total = default_val * k_v_pairs_num
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(expected_total, qset_total)

    def test_populate_monthly_tag_cost_cluster_no_rates(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is not populated when given no tag rates.
        """
        distribution_choices = [metric_constants.CPU_DISTRIBUTION, metric_constants.MEMORY_DISTRIBUTION]
        node_tag_rates = {}
        rate_total = 0

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        for distribution in distribution_choices:
            with self.subTest(distribution=distribution):
                self.cluster_id = "OCP-on-Azure"
                with schema_context(self.schema):
                    # grab one item with the pod_labels we are looking for so the cluster_alias can be gotten
                    k_v = (
                        OCPUsageLineItemDailySummary.objects.filter(pod_labels__contains={"app": "banking"})
                        .values()
                        .first()
                    )
                    c_a = k_v.get("cluster_alias")

                    # create a query set based on the criteria we are looking for
                    # so it can be evaluated before and after the function call
                    qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id,
                        supplementary_monthly_cost_json__isnull=False,
                        monthly_cost_type="Cluster",
                    )
                    # assert that there are no infrastructure monthly node costs currently on our cluster id
                    self.assertEqual(qset.count(), 0)
                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_monthly_tag_cost(
                        "Cluster",
                        "Supplementary",
                        node_tag_rates,
                        start_date,
                        end_date,
                        self.cluster_id,
                        c_a,
                        distribution,
                        self.provider_uuid,
                    )
                    # assert that after the update, there are still no monthly costs for cluster in supplementary
                    self.assertEqual(qset.count(), 0)
                    qset_total = 0
                    for value in qset:
                        qset_total += value.supplementary_monthly_cost_json.get(distribution)
                    # assert that the total value of the qset costs is equal to the total costs from the tag rates
                    self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_cluster_bad_key_value_pairs(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is not populated when the key_value pairs do not match.
        """
        key_value_pairs = {"word": ["pickle", "fridge", "waterfall"]}
        node_tag_rates = {}
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
            node_tag_rates[key] = values_dict

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-Azure"
        with schema_context(self.schema):
            # grab one item with the pod_labels we are looking for so the cluster_alias can be gotten
            k_v = OCPUsageLineItemDailySummary.objects.filter(pod_labels__contains={"app": "banking"}).values().first()
            c_a = k_v.get("cluster_alias")

            # create a query set based on the criteria we are looking for
            # so it can be evaluated before and after the function call
            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, supplementary_monthly_cost_json__isnull=False, monthly_cost_type="Cluster"
            )
            # assert that there are no supplementary monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Cluster",
                "Supplementary",
                node_tag_rates,
                start_date,
                end_date,
                self.cluster_id,
                c_a,
                metric_constants.CPU_DISTRIBUTION,
                self.provider_uuid,
            )
            # assert that after the update, there are still no node costs since the key_value pairs did not match
            self.assertEqual(qset.count(), 0)

    def test_populate_tag_based_usage_costs(self):  # noqa: C901
        """
        Test that the usage costs are updated when tag values are passed in.
        This test runs for both Infrastructure and Supplementary cost types
        as well as all 6 metrics that apply to this update
        and uses subtests that will identify the metric, the tag value, the line item id, and the cost type if it fails.
        """
        # set up the key value pairs to test and the map for cost type and the fields it needs
        key_value_pairs = {"app": ["banking", "mobile", "weather"]}
        cost_type = {
            "cpu_core_usage_per_hour": ["cpu", "pod_usage_cpu_core_hours"],
            "cpu_core_request_per_hour": ["cpu", "pod_request_cpu_core_hours"],
            "memory_gb_usage_per_hour": ["memory", "pod_usage_memory_gigabyte_hours"],
            "memory_gb_request_per_hour": ["memory", "pod_request_memory_gigabyte_hours"],
            "storage_gb_usage_per_month": ["storage", "persistentvolumeclaim_usage_gigabyte_months"],
            "storage_gb_request_per_month": ["storage", "volume_request_storage_gigabyte_months"],
        }

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-AWS"
        with schema_context(self.schema):
            # define the two usage types to test
            usage_types = {"Infrastructure": "infrastructure_usage_cost", "Supplementary": "supplementary_usage_cost"}
            for usage_type, cost_field in usage_types.items():
                # create dictionaries for rates
                for cost, usage_fields in cost_type.items():
                    rate_costs = {}
                    # go through and populate values for the key value pairs for this usage and cost type
                    node_tag_rates = {}
                    for key, values in key_value_pairs.items():
                        values_dict = {}
                        for value in values:
                            node_rate = random.randrange(1, 100)
                            values_dict[value] = node_rate
                        node_tag_rates[key] = values_dict
                    rate_costs[cost] = node_tag_rates
                    # define the arguments for the function based on what usage type needs to be tested
                    if usage_type == "Infrastructure":
                        infrastructure_rates = rate_costs
                        supplementary_rates = {}
                    else:
                        infrastructure_rates = {}
                        supplementary_rates = rate_costs
                    # get the three querysets to be evaluated based on the pod_labels
                    banking_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "banking"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    mobile_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    weather_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "weather"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )

                    # populate a results dictionary for each item in the querysets using the cost before the update
                    initial_results_dict = defaultdict(dict)
                    mapper = {
                        "banking": (banking_qset, {"app": "banking"}),
                        "mobile": (mobile_qset, {"app": "mobile"}),
                        "weather": (weather_qset, {"app": "weather"}),
                    }
                    for word, qset_tuple in mapper.items():
                        qset = qset_tuple[0]
                        for entry in qset:
                            # For each label, by date store the usage, cost
                            initial_results_dict[word][entry.get("usage_start")] = (
                                entry.get("usage") or 0,
                                entry.get("cost") or 0,
                            )

                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_tag_usage_costs(
                        infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
                    )

                    # get the three querysets to be evaluated based on the pod_labels after the update
                    banking_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            pod_labels__contains={"app": "banking"},
                            monthly_cost_type="Tag",
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    mobile_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}, monthly_cost_type="Tag"
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    weather_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            pod_labels__contains={"app": "weather"},
                            monthly_cost_type="Tag",
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )

                    # update the querysets stored in mapper
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    # get the values from after the call and store them in the dictionary
                    post_results_dict = defaultdict(dict)
                    for word, qset in mapper.items():
                        for entry in qset:
                            post_results_dict[word][entry.get("usage_start")] = (
                                entry.get("usage") or 0,
                                entry.get("cost") or 0,
                            )

                    # assert that after the update, the appropriate values were added to each usage_cost
                    # the date check ensures that only entries after start date were updated and the ones
                    # outside the start and end date are not updated
                    for value, rate in rate_costs.get(cost).get("app").items():
                        for day, vals in initial_results_dict.get(value).items():

                            with self.subTest(
                                msg=f"Metric: {cost}, Value: {value}, usage_type: {usage_type}, id: {day}"
                            ):
                                if day >= start_date.date():
                                    expected_diff = float(vals[0] * rate)
                                else:
                                    expected_diff = 0
                                post_record = post_results_dict.get(value, {}).get(day, {})
                                actual_diff = 0
                                if post_record:
                                    actual_diff = float(post_record[1] - vals[1])
                                self.assertAlmostEqual(actual_diff, expected_diff)

    def test_populate_tag_based_default_usage_costs(self):  # noqa: C901
        """Test that the usage costs are updated correctly when default tag values are passed in."""
        # set up the key value pairs to test and the map for cost type and the fields it needs
        cost_type = {
            "cpu_core_usage_per_hour": ["cpu", "pod_usage_cpu_core_hours"],
            "cpu_core_request_per_hour": ["cpu", "pod_request_cpu_core_hours"],
            "memory_gb_usage_per_hour": ["memory", "pod_usage_memory_gigabyte_hours"],
            "memory_gb_request_per_hour": ["memory", "pod_request_memory_gigabyte_hours"],
            "storage_gb_usage_per_month": ["storage", "persistentvolumeclaim_usage_gigabyte_months"],
            "storage_gb_request_per_month": ["storage", "volume_request_storage_gigabyte_months"],
        }

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-AWS"
        with schema_context(self.schema):
            # define the two usage types to test
            usage_types = {"Infrastructure": "infrastructure_usage_cost", "Supplementary": "supplementary_usage_cost"}
            for usage_type, cost_field in usage_types.items():
                # create dictionaries for rates
                for cost, usage_fields in cost_type.items():
                    rate_costs = {}
                    """
                    {
                        'cpu_core_usage_per_hour': {
                            'app': {
                                'default_value': '100.0000000000', 'defined_keys': ['far', 'manager', 'walk']
                        }
                    }
                    """

                    rate_costs[cost] = {
                        "app": {"default_value": random.randrange(1, 100), "defined_keys": ["mobile", "banking"]}
                    }
                    # define the arguments for the function based on what usage type needs to be tested
                    if usage_type == "Infrastructure":
                        infrastructure_rates = rate_costs
                        supplementary_rates = {}
                    else:
                        infrastructure_rates = {}
                        supplementary_rates = rate_costs
                    # get the three querysets to be evaluated based on the pod_labels
                    banking_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "banking"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    mobile_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    weather_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "weather"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )

                    # populate a results dictionary for each item in the querysets using the cost before the update
                    initial_results_dict = defaultdict(dict)
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    for word, qset in mapper.items():
                        for entry in qset:
                            # For each label, by date store the usage, cost
                            initial_results_dict[word][entry.get("usage_start")] = (
                                entry.get("usage") or 0,
                                entry.get("cost") or 0,
                            )

                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_tag_usage_default_costs(
                        infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
                    )

                    # get the three querysets to be evaluated based on the pod_labels after the update
                    banking_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            pod_labels__contains={"app": "banking"},
                            monthly_cost_type="Tag",
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    mobile_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}, monthly_cost_type="Tag"
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    weather_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            pod_labels__contains={"app": "weather"},
                            monthly_cost_type="Tag",
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(KeyDecimalTransform(usage_fields[0], cost_field)),
                            usage=Sum(usage_fields[1]),
                        )
                    )

                    # update the querysets stored in mapper
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    # get the values from after the call and store them in the dictionary
                    post_results_dict = defaultdict(dict)
                    for word, qset in mapper.items():
                        for entry in qset:
                            post_results_dict[word][entry.get("usage_start")] = (
                                entry.get("usage") or 0,
                                entry.get("cost") or 0,
                            )

                    # assert that after the update, the appropriate values were added to each usage_cost
                    # the date check ensures that only entries after start date were updated and the ones
                    # outside the start and end date are not updated
                    for value in mapper:
                        for day, vals in initial_results_dict.get(value).items():
                            with self.subTest(
                                msg=f"Metric: {cost}, Value: {value}, usage_type: {usage_type}, day: {day}"
                            ):
                                if value == "banking" or value == "mobile":
                                    expected_diff = 0
                                else:
                                    if day >= start_date.date():
                                        rate = rate_costs.get(cost).get("app").get("default_value")
                                        expected_diff = float(vals[0] * rate)
                                    else:
                                        expected_diff = 0
                                post_record = post_results_dict.get(value, {}).get(day, {})
                                actual_diff = 0
                                if post_record:
                                    actual_diff = float(post_record[1] - vals[1])
                                self.assertAlmostEqual(actual_diff, expected_diff)

    def test_update_line_item_daily_summary_with_enabled_tags(self):
        """Test that we filter the daily summary table's tags with only enabled tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        report_period = self.accessor.report_periods_for_provider_uuid(self.ocp_provider_uuid, start_date)

        with schema_context(self.schema):
            OCPUsagePodLabelSummary.objects.all().delete()
            OCPStorageVolumeLabelSummary.objects.all().delete()
            key_to_keep = OCPEnabledTagKeys.objects.first()
            OCPEnabledTagKeys.objects.exclude(key=key_to_keep.key).delete()
            report_period_ids = [report_period.id]
            self.accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, report_period_ids)
            tags = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, report_period_id__in=report_period_ids
                )
                .values_list("pod_labels")
                .distinct()
            )

            for tag in tags:
                tag_dict = tag[0] if tag[0] is not None else {}  # Account for possible null
                tag_keys = list(tag_dict.keys())
                if tag_keys:
                    self.assertEqual([key_to_keep.key], tag_keys)
                else:
                    self.assertEqual([], tag_keys)

            tags = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, report_period_id__in=report_period_ids
                )
                .values_list("volume_labels")
                .distinct()
            )

            for tag in tags:
                tag_dict = tag[0] if tag[0] is not None else {}  # Account for possible null
                tag_keys = list(tag_dict.keys())
                if tag_keys:
                    self.assertEqual([key_to_keep.key], tag_keys)
                else:
                    self.assertEqual([], tag_keys)

    def test_delete_line_item_daily_summary_entries_for_date_range(self):
        """Test that daily summary rows are deleted."""
        with schema_context(self.schema):
            start_date = OCPUsageLineItemDailySummary.objects.aggregate(Max("usage_start")).get("usage_start__max")
            end_date = start_date

        table_query = OCPUsageLineItemDailySummary.objects.filter(
            source_uuid=self.ocp_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
        )
        with schema_context(self.schema):
            self.assertNotEqual(table_query.count(), 0)

        self.accessor.delete_line_item_daily_summary_entries_for_date_range(
            self.ocp_provider_uuid, start_date, end_date
        )

        with schema_context(self.schema):
            self.assertEqual(table_query.count(), 0)

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, OCPUsageLineItemDailySummary)

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, OCP_REPORT_TABLE_MAP)
        self.assertEqual(self.accessor._aws_table_map, AWS_CUR_TABLE_MAP)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_get_ocp_infrastructure_map_trino(self, mock_presto):
        """Test that Trino is used to find matched tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        self.accessor.get_ocp_infrastructure_map_trino(start_date, end_date)
        mock_presto.assert_called()

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_get_ocp_infrastructure_map_trino_gcp_resource(self, mock_presto):
        """Test that Trino is used to find matched resource names."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        expected_log = "INFO:masu.util.gcp.common:OCP GCP matching set to resource level"
        with patch(
            "masu.util.gcp.common.ProviderDBAccessor.get_data_source",
            Mock(return_value={"table_id": "resource"}),
        ):
            with self.assertLogs("masu.util.gcp.common", level="INFO") as logger:
                self.accessor.get_ocp_infrastructure_map_trino(
                    start_date, end_date, gcp_provider_uuid=self.gcp_provider_uuid
                )
                mock_presto.assert_called()
                self.assertIn(expected_log, logger.output)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_get_ocp_infrastructure_map_trino_gcp_with_disabled_resource_matching(self, mock_presto):
        """Test that Trino is used to find matched resource names."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        expected_log = f"INFO:masu.util.gcp.common:GCP resource matching disabled for {self.schema}"
        with patch("masu.util.gcp.common.disable_gcp_resource_matching", return_value=True):
            with self.assertLogs("masu", level="INFO") as logger:
                self.accessor.get_ocp_infrastructure_map_trino(
                    start_date, end_date, gcp_provider_uuid=self.gcp_provider_uuid
                )
                mock_presto.assert_called()
                self.assertIn(expected_log, logger.output)

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_projects_presto")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_pvcs_presto")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_nodes_presto")
    def test_populate_openshift_cluster_information_tables(
        self, mock_get_nodes, mock_get_pvcs, mock_get_projects, mock_table
    ):
        """Test that we populate cluster info."""
        nodes = ["test_node_1", "test_node_2"]
        resource_ids = ["id_1", "id_2"]
        capacity = [1, 1]
        volumes = ["vol_1", "vol_2"]
        pvcs = ["pvc_1", "pvc_2"]
        projects = ["project_1", "project_2"]
        roles = ["master", "worker"]
        mock_get_nodes.return_value = zip(nodes, resource_ids, capacity, roles)
        mock_get_pvcs.return_value = zip(volumes, pvcs)
        mock_get_projects.return_value = projects
        mock_table.return_value = True
        cluster_id = uuid.uuid4()
        cluster_alias = "test-cluster-1"
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        self.accessor.populate_openshift_cluster_information_tables(
            self.ocp_provider, cluster_id, cluster_alias, start_date, end_date
        )

        with schema_context(self.schema):
            self.assertIsNotNone(OCPCluster.objects.filter(cluster_id=cluster_id).first())
            for node in nodes:
                db_node = OCPNode.objects.filter(node=node).first()
                self.assertIsNotNone(db_node)
                self.assertIsNotNone(db_node.node)
                self.assertIsNotNone(db_node.resource_id)
                self.assertIsNotNone(db_node.node_capacity_cpu_cores)
                self.assertIsNotNone(db_node.cluster_id)
                self.assertIsNotNone(db_node.node_role)
            for pvc in pvcs:
                self.assertIsNotNone(OCPPVC.objects.filter(persistent_volume_claim=pvc).first())
            for project in projects:
                self.assertIsNotNone(OCPProject.objects.filter(project=project).first())

        mock_table.reset_mock()
        mock_get_pvcs.reset_mock()
        mock_table.return_value = False

        self.accessor.populate_openshift_cluster_information_tables(
            self.ocp_provider, cluster_id, cluster_alias, start_date, end_date
        )
        mock_get_pvcs.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_projects_presto")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_pvcs_presto")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_nodes_presto")
    def test_get_openshift_topology_for_multiple_providers(
        self, mock_get_nodes, mock_get_pvcs, mock_get_projects, mock_table
    ):
        """Test that OpenShift topology is populated."""
        nodes = ["test_node_1", "test_node_2"]
        resource_ids = ["id_1", "id_2"]
        capacity = [1, 1]
        volumes = ["vol_1", "vol_2"]
        pvcs = ["pvc_1", "pvc_2"]
        projects = ["project_1", "project_2"]
        roles = ["master", "worker"]
        mock_get_nodes.return_value = zip(nodes, resource_ids, capacity, roles)
        mock_get_pvcs.return_value = zip(volumes, pvcs)
        mock_get_projects.return_value = projects
        mock_table.return_value = True
        cluster_id = str(uuid.uuid4())
        cluster_alias = "test-cluster-1"
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        # Using the aws_provider to short cut this test instead of creating a brand
        # new provider. The OCP providers already have data, and can't be used here
        self.accessor.populate_openshift_cluster_information_tables(
            self.aws_provider, cluster_id, cluster_alias, start_date, end_date
        )

        with schema_context(self.schema):
            cluster = OCPCluster.objects.filter(cluster_id=cluster_id).first()
            nodes = OCPNode.objects.filter(cluster=cluster).all()
            pvcs = OCPPVC.objects.filter(cluster=cluster).all()
            projects = OCPProject.objects.filter(cluster=cluster).all()
            topology = self.accessor.get_openshift_topology_for_multiple_providers([self.aws_provider])

            self.assertEqual(topology.get("clusters"), [cluster_id])
            self.assertEqual(nodes.count(), len(topology.get("nodes")))
            for node in nodes:
                self.assertIn(node.node, topology.get("nodes"))
            for pvc in pvcs:
                self.assertIn(pvc.persistent_volume_claim, topology.get("persistent_volume_claims"))
                self.assertIn(pvc.persistent_volume, topology.get("persistent_volumes"))
            for project in projects:
                self.assertIn(project.project, topology.get("projects"))

    def test_populate_node_table_update_role(self):
        """Test that populating the node table for an entry that previously existed fills the node role correctly."""
        node_info = ["node_role_test_node", "node_role_test_id", 1, "worker"]
        cluster_id = str(uuid.uuid4())
        cluster_alias = "node_role_test"
        cluster = self.accessor.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
        with schema_context(self.schema):
            node = OCPNode.objects.create(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            )
            self.assertIsNone(node.node_role)
            self.accessor.populate_node_table(cluster, [node_info])
            node = OCPNode.objects.get(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            )
            self.assertEqual(node.node_role, node_info[3])

    def test_populate_node_table_second_time_no_change(self):
        """Test that populating the node table for an entry a second time does not duplicate entries."""
        node_info = ["node_role_test_node", "node_role_test_id", 1, "worker"]
        cluster_id = str(uuid.uuid4())
        cluster_alias = "node_role_test"
        cluster = self.accessor.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
        with schema_context(self.schema):
            self.accessor.populate_node_table(cluster, [node_info])
            node_count = OCPNode.objects.filter(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            ).count()
            self.assertEqual(node_count, 1)
            self.accessor.populate_node_table(cluster, [node_info])
            node_count = OCPNode.objects.filter(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            ).count()
            self.assertEqual(node_count, 1)

    def test_delete_infrastructure_raw_cost_from_daily_summary(self):
        """Test that infra raw cost is deleted."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        report_period = self.accessor.report_periods_for_provider_uuid(self.ocpaws_provider_uuid, start_date)
        with schema_context(self.schema):
            report_period_id = report_period.id
            count = OCPUsageLineItemDailySummary.objects.filter(
                report_period_id=report_period_id, usage_start__gte=start_date, infrastructure_raw_cost__gt=0
            ).count()
        self.assertNotEqual(count, 0)

        self.accessor.delete_infrastructure_raw_cost_from_daily_summary(
            self.ocpaws_provider_uuid, report_period_id, start_date, end_date
        )

        with schema_context(self.schema):
            count = OCPUsageLineItemDailySummary.objects.filter(
                report_period_id=report_period_id, usage_start__gte=start_date, infrastructure_raw_cost__gt=0
            ).count()
        self.assertEqual(count, 0)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_delete_ocp_hive_partition_by_day(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with self.assertRaises(TrinoExternalError):
            self.accessor.delete_ocp_hive_partition_by_day([1], self.ocp_provider_uuid, "2022", "01")
        mock_trino.assert_called()
        # Confirms that the error log would be logged on last attempt
        self.assertEqual(mock_trino.call_args_list[-1].kwargs.get("attempts_left"), 0)
        self.assertEqual(mock_trino.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_delete_hive_partitions_by_source_success(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        result = self.accessor.delete_hive_partitions_by_source("table", "partition_column", self.ocp_provider_uuid)
        mock_trino.assert_called()
        self.assertTrue(result)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_delete_hive_partitions_by_source_failure(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with self.assertRaises(TrinoExternalError):
            result = self.accessor.delete_hive_partitions_by_source(
                "table", "partition_column", self.ocp_provider_uuid
            )
            self.assertFalse(result)
        mock_trino.assert_called()
        # Confirms that the error log would be logged on last attempt
        self.assertEqual(mock_trino.call_args_list[-1].kwargs.get("attempts_left"), 0)
        self.assertEqual(mock_trino.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_presto_raw_sql_query")
    def test_get_max_min_timestamp_from_parquet(self, mock_query):
        """Get the max and min timestamps for parquet data given a date range"""
        start_date, end_date = datetime(2022, 3, 1), datetime(2022, 3, 30)
        table = [
            {
                "name": "valid-dates",
                "return": ["2022-04-01", "2022-04-30"],
                "expected": (datetime(2022, 4, 1), datetime(2022, 4, 30)),
            },
            {"name": "none-dates", "return": [None, None], "expected": (start_date, end_date)},
            {
                "name": "none-start-date",
                "return": [None, "2022-04-30"],
                "expected": (start_date, datetime(2022, 4, 30)),
            },
            {"name": "none-end-date", "return": ["2022-04-01", None], "expected": (datetime(2022, 4, 1), end_date)},
        ]

        for test in table:
            with self.subTest(test=test["name"]):
                mock_query.return_value = [test["return"]]  # returned value is a list of a list
                result = self.accessor.get_max_min_timestamp_from_parquet(uuid.uuid4(), start_date, end_date)
                self.assertEqual(result, test["expected"])
                self.assertTrue(hasattr(result[0], "date"))
                self.assertTrue(hasattr(result[1], "date"))

    def test_delete_all_except_infrastructure_raw_cost_from_daily_summary(self):
        """Test that deleting saves OCP on Cloud data."""
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        # First test an OCP on Cloud source to make sure we don't delete that data
        provider_uuid = self.ocp_on_aws_ocp_provider.uuid
        report_period = self.accessor.report_periods_for_provider_uuid(provider_uuid, start_date)

        with schema_context(self.schema):
            report_period_id = report_period.id
            initial_non_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()
            initial_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

        self.accessor.delete_all_except_infrastructure_raw_cost_from_daily_summary(
            provider_uuid, report_period_id, start_date, end_date
        )

        with schema_context(self.schema):
            new_non_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()
            new_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

        self.assertNotEqual(initial_non_raw_count, 0)
        self.assertEqual(new_non_raw_count, 0)
        self.assertEqual(initial_raw_count, new_raw_count)

        # Now test an on prem OCP cluster to make sure we still remove non raw costs
        provider_uuid = self.ocp_provider.uuid
        report_period = self.accessor.report_periods_for_provider_uuid(provider_uuid, start_date)

        with schema_context(self.schema):
            report_period_id = report_period.id
            initial_non_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()
            initial_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

        self.accessor.delete_all_except_infrastructure_raw_cost_from_daily_summary(
            provider_uuid, report_period_id, start_date, end_date
        )

        with schema_context(self.schema):
            new_non_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()
            new_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

        self.assertNotEqual(initial_non_raw_count, new_non_raw_count)
        self.assertEqual(initial_raw_count, 0)
        self.assertEqual(new_raw_count, 0)
