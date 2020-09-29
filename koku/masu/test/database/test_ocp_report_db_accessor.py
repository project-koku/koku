#
# Copyright 2018 Red Hat, Inc.
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
"""Test the OCPReportDBAccessor utility object."""
import random
import string

from dateutil import relativedelta
from django.db import connection
from django.db.models import Max
from django.db.models import Min
from django.db.models.query import QuerySet
from django_tenants.utils import schema_context

from api.metrics import constants as metric_constants
from api.utils import DateHelper
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.util.common import month_date_range_tuple
from reporting.models import OCPUsageLineItem
from reporting.models import OCPUsageLineItemDailySummary
from reporting.models import OCPUsageReport
from reporting.models import OCPUsageReportPeriod
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
        self.accessor.populate_storage_line_item_daily_summary_table(start_date, end_date, cluster_id)

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
        self.accessor.populate_line_item_daily_summary_table(start_date, end_date, cluster_id)
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
        current_report_period = self.accessor.get_current_usage_period()
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

        periods = self.accessor.report_periods_for_provider_uuid(provider_uuid, start_date)
        with schema_context(self.schema):
            self.assertGreater(len(periods), 0)

            period = periods[0]

            self.assertEqual(period.provider_id, provider_uuid)

    def test_get_lineitem_query_for_reportid(self):
        """Test that the line item data is returned given a report_id."""
        current_report = self.accessor.get_current_usage_report()
        with schema_context(self.schema):
            self.assertIsNotNone(current_report.report_period_id)
            report_id = current_report.id
            initial_count = OCPUsageLineItem.objects.filter(report_id=report_id).count()
        line_item_query = self.accessor.get_lineitem_query_for_reportid(report_id)
        with schema_context(self.schema):
            self.assertEqual(line_item_query.count(), initial_count)
            self.assertEqual(line_item_query.first().report_id, report_id)

            query_report = line_item_query.first()
            self.assertIsNotNone(query_report.namespace)
            self.assertIsNotNone(query_report.pod)
            self.assertIsNotNone(query_report.node)
            self.assertIsNotNone(query_report.pod_usage_cpu_core_seconds)
            self.assertIsNotNone(query_report.pod_request_cpu_core_seconds)
            self.assertIsNotNone(query_report.pod_limit_cpu_core_seconds)
            self.assertIsNotNone(query_report.pod_usage_memory_byte_seconds)
            self.assertIsNotNone(query_report.pod_request_memory_byte_seconds)
            self.assertIsNotNone(query_report.pod_limit_memory_byte_seconds)

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

    def test_populate_line_item_daily_summary_table(self):
        """Test that the line item daily summary table populates."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        summary_table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        report_table = getattr(self.accessor.report_schema, report_table_name)
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

            query = self.accessor._get_db_obj_query(summary_table_name)

            self.accessor.populate_node_label_line_item_daily_table(start_date, end_date, self.cluster_id)
            self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)
            self.accessor.populate_line_item_daily_summary_table(start_date, end_date, self.cluster_id)

            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = summary_entry["usage_start__min"]
            result_end_date = summary_entry["usage_start__max"]

            self.assertEqual(result_start_date, start_date.date())
            self.assertEqual(result_end_date, end_date.date())

            entry = query.first()

        summary_columns = [
            "cluster_id",
            "namespace",
            "node",
            "node_capacity_cpu_core_hours",
            "node_capacity_cpu_cores",
            "node_capacity_memory_gigabyte_hours",
            "node_capacity_memory_gigabytes",
            "pod_labels",
            "pod_limit_cpu_core_hours",
            "pod_limit_memory_gigabyte_hours",
            "pod_request_cpu_core_hours",
            "pod_request_memory_gigabyte_hours",
            "pod_usage_cpu_core_hours",
            "pod_usage_memory_gigabyte_hours",
            "usage_end",
            "usage_start",
        ]

        for column in summary_columns:
            self.assertIsNotNone(getattr(entry, column))

    def test_populate_pod_label_summary_table(self):
        """Test that the pod label summary table is populated."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        agg_table_name = OCP_REPORT_TABLE_MAP["pod_label_summary"]

        report_table = getattr(self.accessor.report_schema, report_table_name)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(agg_table_name)

        with schema_context(self.schema):
            tags = query.all()
            tag_keys = list({tag.key for tag in tags})

            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT DISTINCT jsonb_object_keys(pod_labels)
                        FROM reporting_ocpusagelineitem_daily"""
                )

                expected_tag_keys = cursor.fetchall()
                expected_tag_keys = [tag[0] for tag in expected_tag_keys]

            self.assertEqual(sorted(tag_keys), sorted(expected_tag_keys))

    def test_populate_volume_label_summary_table(self):
        """Test that the volume label summary table is populated."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        agg_table_name = OCP_REPORT_TABLE_MAP["volume_label_summary"]

        report_table = getattr(self.accessor.report_schema, report_table_name)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(agg_table_name)
        self.accessor.populate_volume_label_summary_table([self.reporting_period.id])

        with schema_context(self.schema):
            tags = query.all()
            tag_keys = list({tag.key for tag in tags})

            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT DISTINCT jsonb_object_keys(persistentvolume_labels || persistentvolumeclaim_labels)
                        FROM reporting_ocpstoragelineitem_daily"""
                )

                expected_tag_keys = cursor.fetchall()
                expected_tag_keys = [tag[0] for tag in expected_tag_keys]

        self.assertEqual(sorted(tag_keys), sorted(expected_tag_keys))

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

    def test_get_item_query_report_period_id(self):
        """Test that gets a usage report line item query given a report period id."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]

        with schema_context(self.schema):
            # Verify that the line items for the test report_period_id are returned
            report_period_id = self.accessor._get_db_obj_query(table_name).first().id
        line_item_query = self.accessor.get_item_query_report_period_id(report_period_id)
        with schema_context(self.schema):
            self.assertEqual(line_item_query.first().report_period_id, report_period_id)

            # Verify that no line items are returned for a missing report_period_id
            wrong_report_period_id = report_period_id + 5
        line_item_query = self.accessor.get_item_query_report_period_id(wrong_report_period_id)
        with schema_context(self.schema):
            self.assertEqual(line_item_query.count(), 0)

    def test_get_report_query_report_period_id(self):
        """Test that gets a usage report item query given a report period id."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]

        with schema_context(self.schema):
            # Verify that the line items for the test report_period_id are returned
            report_period_id = self.accessor._get_db_obj_query(table_name).first().id
        usage_report_query = self.accessor.get_report_query_report_period_id(report_period_id)
        with schema_context(self.schema):
            self.assertEqual(usage_report_query.first().report_period_id, report_period_id)

            # Verify that no line items are returned for a missing report_period_id
            wrong_report_period_id = report_period_id + 5
        usage_report_query = self.accessor.get_report_query_report_period_id(wrong_report_period_id)
        with schema_context(self.schema):
            self.assertEqual(usage_report_query.count(), 0)

    def test_get_pod_cpu_core_hours(self):
        """Test that gets pod cpu usage/request."""
        start_date, end_date = self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        # Verify that the line items for the test cluster_id are returned
        cluster_id = self.accessor._get_db_obj_query(table_name).first().cluster_id
        reports = self.accessor._get_db_obj_query(table_name).filter(
            cluster_id=cluster_id, usage_start__gte=start_date, usage_start__lte=end_date, data_source="Pod"
        )

        expected_usage_reports = {entry.id: entry.pod_usage_cpu_core_hours for entry in reports}
        expected_request_reports = {entry.id: entry.pod_usage_cpu_core_hours for entry in reports}
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
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source="Pod").all()

        expected_usage_reports = {entry.id: entry.pod_usage_cpu_core_hours for entry in reports}
        expected_request_reports = {entry.id: entry.pod_usage_cpu_core_hours for entry in reports}
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

        expected_usage_reports = {entry.id: entry.pod_usage_memory_gigabyte_hours for entry in reports}
        expected_request_reports = {entry.id: entry.pod_request_memory_gigabyte_hours for entry in reports}
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
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source="Pod").all()

        expected_usage_reports = {entry.id: entry.pod_usage_memory_gigabyte_hours for entry in reports}
        expected_request_reports = {entry.id: entry.pod_request_memory_gigabyte_hours for entry in reports}
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

        expected_usage_reports = {entry.id: entry.persistentvolumeclaim_usage_gigabyte_months for entry in reports}
        expected_request_reports = {entry.id: entry.volume_request_storage_gigabyte_months for entry in reports}
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
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source="Storage").all()

        expected_usage_reports = {entry.id: entry.persistentvolumeclaim_usage_gigabyte_months for entry in reports}
        expected_request_reports = {entry.id: entry.volume_request_storage_gigabyte_months for entry in reports}
        vol_usage_query = self.accessor.get_persistentvolumeclaim_usage_gigabyte_months(start_date, end_date)
        vol_request_query = self.accessor.get_volume_request_storage_gigabyte_months(start_date, end_date)

        self.assertEqual(len(vol_usage_query.keys()), len(expected_usage_reports.keys()))
        self.assertEqual(len(vol_request_query.keys()), len(expected_request_reports.keys()))

    def test_get_daily_usage_query_for_clusterid(self):
        """Test that daily usage getter is correct."""
        self._populate_pod_summary()
        daily_usage = self.accessor.get_daily_usage_query_for_clusterid(self.cluster_id)
        self.assertEquals(daily_usage.count(), 26)

    def test_get_summary_usage_query_for_clusterid(self):
        """Test that daily usage summary getter is correct."""
        daily_usage_summary = self.accessor.get_summary_usage_query_for_clusterid(self.cluster_id)
        with schema_context(self.schema):
            self.assertEquals(daily_usage_summary.count(), 0)
        self._populate_pod_summary()
        with schema_context(self.schema):
            self.assertEquals(daily_usage_summary.count(), 26)

    def test_get_storage_item_query_report_period_id(self):
        """Test that get_storage_item_query_report_period_id is correct."""
        storage_line_item = self.accessor.get_storage_item_query_report_period_id(self.reporting_period.id)
        with schema_context(self.schema):
            self.assertEquals(storage_line_item.count(), 1)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEquals(storage_line_item.count(), 26)

    def test_get_daily_storage_item_query_cluster_id(self):
        """Test that get_daily_storage_item_query_cluster_id is correct."""
        with schema_context(self.schema):
            storage_line_item = self.accessor.get_daily_storage_item_query_cluster_id(self.cluster_id)
            self.assertEquals(storage_line_item.count(), 0)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEquals(storage_line_item.count(), 26)

    def test_get_storage_summary_query_cluster_id(self):
        """Test that get_storage_summary_query_cluster_id is correct."""
        storage_summary = self.accessor.get_storage_summary_query_cluster_id(self.cluster_id)
        with schema_context(self.schema):
            self.assertEquals(storage_summary.count(), 0)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEquals(storage_summary.count(), 26)

    def test_get_report_periods(self):
        """Test that report_periods getter is correct."""
        with schema_context(self.schema):
            periods = self.accessor.get_report_periods()
            self.assertEquals(len(periods), OCPUsageReportPeriod.objects.count())

    def test_get_reports(self):
        """Test that the report getter is correct."""
        with schema_context(self.schema):
            reports = self.accessor.get_reports()
            self.assertEquals(len(reports), OCPUsageReport.objects.count())

    def test_populate_monthly_cost_node_infrastructure_cost(self):
        """Test that the monthly infrastructure cost row for nodes in the summary table is populated."""
        self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")

        node_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, _ = month_date_range_tuple(start_date)

        cluster_alias = "test_cluster_alias"
        self.accessor.populate_monthly_cost(
            "Node", "Infrastructure", node_rate, start_date, end_date, self.cluster_id, cluster_alias
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, infrastructure_monthly_cost__isnull=False)
            .all()
        )
        with schema_context(self.schema):
            expected_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    report_period__provider_id=self.ocp_provider.uuid, usage_start__gte=start_date
                )
                .values("node")
                .distinct()
                .count()
            )
            self.assertEquals(monthly_cost_rows.count(), expected_count)
            for monthly_cost_row in monthly_cost_rows:
                self.assertEquals(monthly_cost_row.infrastructure_monthly_cost, node_rate)

    def test_populate_monthly_cost_node_supplementary_cost(self):
        """Test that the monthly supplementary cost row for nodes in the summary table is populated."""
        self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")

        node_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, _ = month_date_range_tuple(start_date)

        cluster_alias = "test_cluster_alias"
        self.accessor.populate_monthly_cost(
            "Node", "Supplementary", node_rate, start_date, end_date, self.cluster_id, cluster_alias
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, supplementary_monthly_cost__isnull=False)
            .all()
        )
        with schema_context(self.schema):
            expected_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    report_period__provider_id=self.ocp_provider.uuid, usage_start__gte=start_date
                )
                .values("node")
                .distinct()
                .count()
            )
            self.assertEquals(monthly_cost_rows.count(), expected_count)
            for monthly_cost_row in monthly_cost_rows:
                self.assertEquals(monthly_cost_row.supplementary_monthly_cost, node_rate)

    def test_populate_monthly_cost_cluster_infrastructure_cost(self):
        """Test that the monthly infrastructure cost row for clusters in the summary table is populated."""
        self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")

        cluster_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, _ = month_date_range_tuple(start_date)

        cluster_alias = "test_cluster_alias"
        self.accessor.populate_monthly_cost(
            "Cluster", "Infrastructure", cluster_rate, start_date, end_date, self.cluster_id, cluster_alias
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, infrastructure_monthly_cost__isnull=False)
            .all()
        )
        with schema_context(self.schema):
            self.assertEquals(monthly_cost_rows.count(), 1)
            for monthly_cost_row in monthly_cost_rows:
                self.assertEquals(monthly_cost_row.infrastructure_monthly_cost, cluster_rate)

    def test_populate_monthly_cost_cluster_supplementary_cost(self):
        """Test that the monthly infrastructure cost row for clusters in the summary table is populated."""
        self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")

        cluster_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, _ = month_date_range_tuple(start_date)

        cluster_alias = "test_cluster_alias"
        self.accessor.populate_monthly_cost(
            "Cluster", "Supplementary", cluster_rate, start_date, end_date, self.cluster_id, cluster_alias
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, supplementary_monthly_cost__isnull=False)
            .all()
        )
        with schema_context(self.schema):
            self.assertEquals(monthly_cost_rows.count(), 1)
            for monthly_cost_row in monthly_cost_rows:
                self.assertEquals(monthly_cost_row.supplementary_monthly_cost, cluster_rate)

    def test_remove_monthly_cost(self):
        """Test that the monthly cost row in the summary table is removed."""
        self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")

        node_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, first_next_month = month_date_range_tuple(start_date)

        cluster_alias = "test_cluster_alias"
        cost_type = "Node"
        rate_type = metric_constants.SUPPLEMENTARY_COST_TYPE
        self.accessor.populate_monthly_cost(
            cost_type, rate_type, node_rate, start_date, end_date, self.cluster_id, cluster_alias
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, supplementary_monthly_cost__isnull=False)
            .all()
        )
        with schema_context(self.schema):
            self.assertTrue(monthly_cost_rows.exists())
        self.accessor.remove_monthly_cost(start_date, first_next_month, self.cluster_id, cost_type)
        with schema_context(self.schema):
            self.assertFalse(monthly_cost_rows.exists())

    def test_remove_monthly_cost_no_data(self):
        """Test that an error isn't thrown when the monthly cost row has no data."""
        start_date = DateAccessor().today_with_timezone("UTC")
        end_date = DateAccessor().today_with_timezone("UTC")
        cost_type = "Node"

        try:
            self.accessor.remove_monthly_cost(start_date, end_date, self.cluster_id, cost_type)
        except Exception as err:
            self.fail(f"Exception thrown: {err}")

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

    def test_upsert_monthly_cluster_cost_line_item(self):
        """Test that the cluster monthly costs are not updated."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        report_table = getattr(self.accessor.report_schema, report_table_name)
        rate = 1000
        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

            start_date = str(self.reporting_period.report_period_start)
            end_date = str(self.reporting_period.report_period_end)
            self.accessor.upsert_monthly_cluster_cost_line_item(
                start_date, end_date, self.cluster_id, "cluster_alias", metric_constants.SUPPLEMENTARY_COST_TYPE, rate
            )
            summary_table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
            query = self.accessor._get_db_obj_query(summary_table_name)
            self.assertEqual(query.filter(cluster_id=self.cluster_id).first().supplementary_monthly_cost, rate)

    def test_upsert_monthly_cluster_cost_line_item_no_report_period(self):
        """Test that the cluster monthly costs are not updated when no report period  is found."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        report_table = getattr(self.accessor.report_schema, report_table_name)
        rate = 1000

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            self.accessor.upsert_monthly_cluster_cost_line_item(
                start_date, end_date, self.cluster_id, "cluster_alias", metric_constants.SUPPLEMENTARY_COST_TYPE, rate
            )
            summary_table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
            query = self.accessor._get_db_obj_query(summary_table_name)
            self.assertFalse(query.filter(cluster_id=self.cluster_id).exists())
