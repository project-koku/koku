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
from tenant_schemas.utils import schema_context

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
            pod_entry = query.filter(data_source="Pod").first()
            storage_entry = query.filter(data_source="Storage").first()

        pod_summary_columns = [
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

        storage_summary_columns = [
            "cluster_id",
            "namespace",
            "node",
            "persistentvolume",
            "persistentvolumeclaim",
            "persistentvolumeclaim_capacity_gigabyte",
            "persistentvolumeclaim_capacity_gigabyte_months",
            "persistentvolumeclaim_usage_gigabyte_months",
            "storageclass",
            "volume_labels",
            "volume_request_storage_gigabyte_months",
            "usage_end",
            "usage_start",
        ]

        for column in pod_summary_columns:
            print((column, getattr(pod_entry, column)))
            self.assertIsNotNone(getattr(pod_entry, column))
        for column in storage_summary_columns:
            self.assertIsNotNone(getattr(storage_entry, column))

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
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source="Pod").all()

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
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source="Pod").all()

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
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source="Storage").all()

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

    def test_populate_monthly_cost_pvc_infrastructure_cost(self):
        """Test that the monthly infrastructure cost row for PVC in the summary table is populated."""
        self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")

        pvc_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, _ = month_date_range_tuple(start_date)

        cluster_alias = "test_cluster_alias"
        self.accessor.populate_monthly_cost(
            "PVC", "Infrastructure", pvc_rate, start_date, end_date, self.cluster_id, cluster_alias
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, infrastructure_monthly_cost__isnull=False)
            .all()
        )
        with schema_context(self.schema):
            expected_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    report_period__provider_id=self.ocp_provider.uuid,
                    usage_start__gte=start_date,
                    persistentvolumeclaim__isnull=False,
                )
                .values("persistentvolumeclaim")
                .distinct()
                .count()
            )
            self.assertEquals(monthly_cost_rows.count(), expected_count)
            for monthly_cost_row in monthly_cost_rows:
                self.assertEquals(monthly_cost_row.infrastructure_monthly_cost, pvc_rate)

    def test_populate_monthly_cost_pvc_supplementary_cost(self):
        """Test that the monthly supplementary cost row for PVC in the summary table is populated."""
        self.cluster_id = self.ocp_provider.authentication.credentials.get("cluster_id")

        pvc_rate = random.randrange(1, 100)

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        first_month, _ = month_date_range_tuple(start_date)

        cluster_alias = "test_cluster_alias"
        self.accessor.populate_monthly_cost(
            "PVC", "Supplementary", pvc_rate, start_date, end_date, self.cluster_id, cluster_alias
        )

        monthly_cost_rows = (
            self.accessor._get_db_obj_query(OCPUsageLineItemDailySummary)
            .filter(usage_start=first_month, supplementary_monthly_cost__isnull=False)
            .all()
        )
        with schema_context(self.schema):
            expected_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    report_period__provider_id=self.ocp_provider.uuid,
                    usage_start__gte=start_date,
                    persistentvolumeclaim__isnull=False,
                )
                .values("persistentvolumeclaim")
                .distinct()
                .count()
            )
            self.assertEquals(monthly_cost_rows.count(), expected_count)
            for monthly_cost_row in monthly_cost_rows:
                self.assertEquals(monthly_cost_row.supplementary_monthly_cost, pvc_rate)

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

    # tag based testing is below
    def test_populate_monthly_tag_cost_node_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for nodes in the summary table
        is populated when given tag based rates.
        """
        key_value_pairs = {"app": ["banking", "mobile", "weather"]}
        node_tag_rates = {}
        rate_total = 0
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
                rate_total += node_rate
            node_tag_rates[key] = values_dict

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-Azure"
        with schema_context(self.schema):
            k_v = OCPUsageLineItemDailySummary.objects.filter(pod_labels__contains={"app": "banking"}).values().first()
            c_a = k_v.get("cluster_alias")

            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, infrastructure_monthly_cost__isnull=False, monthly_cost_type="Node"
            ).values("infrastructure_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Node", "Infrastructure", node_tag_rates, start_date, end_date, self.cluster_id, c_a
            )

            # assert that after the update, there are now the monthly values
            # for the three different nodes that have a value
            self.assertEqual(qset.count(), 3)
            qset_total = 0
            for value in qset:
                qset_total += value.get("infrastructure_monthly_cost")
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_pvc_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for PVCs in the summary table
        is populated when given tag based rates.
        """
        key_value_pairs = {"app": ["banking", "mobile", "weather"]}
        pvc_tag_rates = {}
        rate_total = 0
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                pvc_rate = random.randrange(1, 100)
                values_dict[value] = pvc_rate
                if value == "mobile":
                    rate_total += pvc_rate
                rate_total += pvc_rate
            pvc_tag_rates[key] = values_dict

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-Azure"
        with schema_context(self.schema):
            k_v = (
                OCPUsageLineItemDailySummary.objects.filter(volume_labels__contains={"app": "banking"})
                .values()
                .first()
            )
            c_a = k_v.get("cluster_alias")

            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, infrastructure_monthly_cost__isnull=False, monthly_cost_type="PVC"
            ).values("infrastructure_monthly_cost")
            # assert that there are no infrastructure monthly PVC costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "PVC", "Infrastructure", pvc_tag_rates, start_date, end_date, self.cluster_id, c_a
            )

            # assert that after the update, there are now the monthly values
            # for the three different PVCs that have a value
            self.assertEqual(qset.count(), 4)
            qset_total = 0
            for value in qset:
                qset_total += value.get("infrastructure_monthly_cost")
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_node_supplementary_cost(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is populated when given tag based rates.
        """
        key_value_pairs = {"app": ["banking", "mobile", "weather"]}
        node_tag_rates = {}
        rate_total = 0
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
                rate_total += node_rate
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
                cluster_id=self.cluster_id, supplementary_monthly_cost__isnull=False, monthly_cost_type="Node"
            ).values("supplementary_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Node", "Supplementary", node_tag_rates, start_date, end_date, self.cluster_id, c_a
            )
            print("\n\n\n\n\n")
            print(
                OCPUsageLineItemDailySummary.objects.filter(
                    cluster_id=self.cluster_id, pod_labels__contains='{"app":"banking"}'
                ).values("pod_labels")
            )
            print("\n\n\n\n\n")
            print(c_a)
            # assert that after the update, there are now the monthly values for
            # the three different nodes that have a value
            self.assertEqual(qset.count(), 3)
            qset_total = 0
            for value in qset:
                qset_total += value.get("supplementary_monthly_cost")
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_pvc_supplementary_cost(self):
        """
        Test that the monthly supplementary cost row for PVCs in the summary table
        is populated when given tag based rates.
        """
        key_value_pairs = {"app": ["banking", "mobile", "weather"]}
        pvc_tag_rates = {}
        rate_total = 0
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                pvc_rate = random.randrange(1, 100)
                values_dict[value] = pvc_rate
                if value == "mobile":
                    rate_total += pvc_rate
                rate_total += pvc_rate
            pvc_tag_rates[key] = values_dict

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-Azure"
        with schema_context(self.schema):
            # grab one item with the pod_labels we are looking for so the cluster_alias can be gotten
            k_v = (
                OCPUsageLineItemDailySummary.objects.filter(volume_labels__contains={"app": "banking"})
                .values()
                .first()
            )
            c_a = k_v.get("cluster_alias")

            # create a query set based on the criteria we are looking for
            # so it can be evaluated before and after the function call
            qset = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, supplementary_monthly_cost__isnull=False, monthly_cost_type="PVC"
            ).values("supplementary_monthly_cost")
            # assert that there are no infrastructure monthly PVC costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "PVC", "Supplementary", pvc_tag_rates, start_date, end_date, self.cluster_id, c_a
            )
            # assert that after the update, there are now the monthly values for
            # the three different PVCs that have a value
            self.assertEqual(qset.count(), 4)
            qset_total = 0
            for value in qset:
                qset_total += value.get("supplementary_monthly_cost")
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_node_no_rates(self):
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
                cluster_id=self.cluster_id, supplementary_monthly_cost__isnull=False, monthly_cost_type="Node"
            ).values("supplementary_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Node", "Supplementary", node_tag_rates, start_date, end_date, self.cluster_id, c_a
            )
            # assert that after the update, there are still no monthly costs for nodes in supplementary
            self.assertEqual(qset.count(), 0)
            qset_total = 0
            for value in qset:
                qset_total += value.get("supplementary_monthly_cost", 0)
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
                cluster_id=self.cluster_id, supplementary_monthly_cost__isnull=False, monthly_cost_type="PVC"
            ).values("supplementary_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "PVC", "Supplementary", node_tag_rates, start_date, end_date, self.cluster_id, c_a
            )
            # assert that after the update, there are still no monthly costs for nodes in supplementary
            self.assertEqual(qset.count(), 0)
            qset_total = 0
            for value in qset:
                qset_total += value.get("supplementary_monthly_cost", 0)
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
                cluster_id=self.cluster_id, supplementary_monthly_cost__isnull=False, monthly_cost_type="Node"
            ).values("supplementary_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Node", "Supplementary", node_tag_rates, start_date, end_date, self.cluster_id, c_a
            )
            # assert that after the update, there are still no node costs since the key_value pairs did not match
            self.assertEqual(qset.count(), 0)

    def test_populate_monthly_tag_cost_cluster_infrastructure_cost(self):
        """
        Test that the monthly infrastructure cost row for cluster in the summary table
        is populated when given tag based rates.
        """
        key_value_pairs = {"app": ["banking", "mobile", "weather"]}
        node_tag_rates = {}
        rate_total = 0
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
                rate_total += node_rate
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
                cluster_id=self.cluster_id, infrastructure_monthly_cost__isnull=False, monthly_cost_type="Cluster"
            ).values("infrastructure_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Cluster", "Infrastructure", node_tag_rates, start_date, end_date, self.cluster_id, c_a
            )
            # assert that after the update, there is now the value for the cluster we specified
            self.assertEqual(qset.count(), 1)
            qset_total = 0
            for value in qset:
                qset_total += value.get("infrastructure_monthly_cost")
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_cluster_supplementary_cost(self):
        """
        Test that the monthly supplementary cost row for nodes in the summary table
        is populated when given tag based rates.
        """
        key_value_pairs = {"app": ["banking", "mobile", "weather"]}
        node_tag_rates = {}
        rate_total = 0
        for key, values in key_value_pairs.items():
            values_dict = {}
            for value in values:
                node_rate = random.randrange(1, 100)
                values_dict[value] = node_rate
                rate_total += node_rate
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
                cluster_id=self.cluster_id, supplementary_monthly_cost__isnull=False, monthly_cost_type="Cluster"
            ).values("supplementary_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Cluster", "Supplementary", node_tag_rates, start_date, end_date, self.cluster_id, c_a
            )
            # assert that after the update, there is now the value for the cluster we specified
            self.assertEqual(qset.count(), 1)
            qset_total = 0
            for value in qset:
                qset_total += value.get("supplementary_monthly_cost")
            # assert that the total value of the qset costs is equal to the total costs from the tag rates
            self.assertEqual(rate_total, qset_total)

    def test_populate_monthly_tag_cost_cluster_no_rates(self):
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
                cluster_id=self.cluster_id, supplementary_monthly_cost__isnull=False, monthly_cost_type="Cluster"
            ).values("supplementary_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Cluster", "Supplementary", node_tag_rates, start_date, end_date, self.cluster_id, c_a
            )
            # assert that after the update, there are still no monthly costs for cluster in supplementary
            self.assertEqual(qset.count(), 0)
            qset_total = 0
            for value in qset:
                qset_total += value.get("supplementary_monthly_cost", 0)
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
                cluster_id=self.cluster_id, supplementary_monthly_cost__isnull=False, monthly_cost_type="Cluster"
            ).values("supplementary_monthly_cost")
            # assert that there are no infrastructure monthly node costs currently on our cluster id
            self.assertEqual(qset.count(), 0)
            # call populate monthly tag_cost with the rates defined above
            self.accessor.populate_monthly_tag_cost(
                "Cluster", "Supplementary", node_tag_rates, start_date, end_date, self.cluster_id, c_a
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
        self.cluster_id = "OCP-on-Azure"
        with schema_context(self.schema):
            # define the two usage types to test
            usage_types = {"Infrastructure": "infrastructure_usage_cost", "Supplementary": "supplementary_usage_cost"}
            for usage_type, field in usage_types.items():
                # create dictionaries for rates
                for cost, cost_fields in cost_type.items():
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
                    banking_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "banking"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")
                    mobile_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")
                    weather_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "weather"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")

                    # populate a results dictionary for each item in the querysets using the cost before the update
                    results_dict = {}
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    for word, qset in mapper.items():
                        temp_dict = {}
                        for i in qset:
                            hours = i.get(cost_fields[1])
                            if hours is None:
                                hours = 0
                            temp_dict[i.get("uuid")] = {
                                "before": i.get(field),
                                "hours": hours,
                                "usage_start": i.get("usage_start"),
                            }
                        results_dict[word] = temp_dict

                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_tag_usage_costs(
                        infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
                    )

                    # get the three querysets to be evaluated based on the pod_labels after the update
                    banking_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "banking"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")
                    mobile_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")
                    weather_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "weather"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")

                    # update the querysets stored in mapper
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    # get the values from after the call and store them in the dictionary
                    for word, qset in mapper.items():
                        existing_dict = results_dict.get(word)
                        for i in qset:
                            exist = existing_dict.get(i.get("uuid"))
                            exist["after"] = i.get(field)

                    # assert that after the update, the appropriate values were added to each usage_cost
                    # the date check ensures that only entries after start date were updated and the ones
                    # outside the start and end date are not updated
                    for value, rate in rate_costs.get(cost).get("app").items():
                        for item, vals in results_dict.get(value).items():

                            with self.subTest(
                                msg=f"Metric: {cost}, Value: {value}, usage_type: {usage_type}, id: {item}"
                            ):
                                if vals.get("usage_start") >= start_date.date():
                                    expected_diff = float(vals.get("hours") * rate)
                                else:
                                    expected_diff = 0
                                actual_diff = vals.get("after").get(cost_fields[0]) - vals.get("before").get(
                                    cost_fields[0]
                                )
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
        self.cluster_id = "OCP-on-Azure"
        with schema_context(self.schema):
            # define the two usage types to test
            usage_types = {"Infrastructure": "infrastructure_usage_cost", "Supplementary": "supplementary_usage_cost"}
            for usage_type, field in usage_types.items():
                # create dictionaries for rates
                for cost, cost_fields in cost_type.items():
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
                    banking_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "banking"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")
                    mobile_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")
                    weather_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "weather"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")

                    # populate a results dictionary for each item in the querysets using the cost before the update
                    results_dict = {}
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    for word, qset in mapper.items():
                        temp_dict = {}
                        for i in qset:
                            hours = i.get(cost_fields[1])
                            if hours is None:
                                hours = 0
                            temp_dict[i.get("uuid")] = {
                                "before": i.get(field, 0),
                                "hours": hours,
                                "usage_start": i.get("usage_start"),
                            }
                        results_dict[word] = temp_dict

                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_tag_usage_default_costs(
                        infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
                    )

                    # get the three querysets to be evaluated based on the pod_labels after the update
                    banking_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "banking"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")
                    mobile_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")
                    weather_qset = OCPUsageLineItemDailySummary.objects.filter(
                        cluster_id=self.cluster_id, pod_labels__contains={"app": "weather"}
                    ).values(field, "uuid", cost_fields[1], "usage_start")

                    # update the querysets stored in mapper
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    # get the values from after the call and store them in the dictionary
                    for word, qset in mapper.items():
                        existing_dict = results_dict.get(word)
                        for i in qset:
                            exist = existing_dict.get(i.get("uuid"))
                            exist["after"] = i.get(field)

                    # assert that after the update, the appropriate values were added to each usage_cost
                    # the date check ensures that only entries after start date were updated and the ones
                    # outside the start and end date are not updated
                    for value in mapper:
                        for item, vals in results_dict.get(value).items():
                            with self.subTest(
                                msg=f"Metric: {cost}, Value: {value}, usage_type: {usage_type}, id: {item}"
                            ):
                                if value == "banking" or value == "mobile":
                                    expected_diff = 0
                                else:
                                    if vals.get("usage_start") >= start_date.date():
                                        rate = rate_costs.get(cost).get("app").get("default_value")
                                        expected_diff = float(vals.get("hours") * rate)
                                    else:
                                        expected_diff = 0
                                actual_diff = vals.get("after").get(cost_fields[0]) - vals.get("before").get(
                                    cost_fields[0]
                                )
                                self.assertAlmostEqual(actual_diff, expected_diff)
