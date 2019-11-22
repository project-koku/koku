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
from django.db.models import Max, Min, Sum
from django.db.models.query import QuerySet
from tenant_schemas.utils import schema_context

from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.util.common import month_date_range_tuple
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


class OCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the OCPReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.common_accessor = ReportingCommonDBAccessor()
        cls.column_map = cls.common_accessor.column_map
        cls.accessor = OCPReportDBAccessor(schema=cls.schema, column_map=cls.column_map)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema, cls.column_map)
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

        self.cluster_id = 'testcluster'

        with ProviderDBAccessor(
            provider_uuid=self.ocp_test_provider_uuid
        ) as provider_accessor:
            self.ocp_provider_uuid = provider_accessor.get_provider().uuid

        self.reporting_period = self.creator.create_ocp_report_period(
            provider_uuid=self.ocp_provider_uuid, cluster_id=self.cluster_id
        )
        self.report = self.creator.create_ocp_report(self.reporting_period)
        pod = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
        namespace = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
        self.creator.create_ocp_usage_line_item(
            self.reporting_period,
            self.report,
            pod=pod,
            namespace=namespace
        )
        self.creator.create_ocp_storage_line_item(
            self.reporting_period,
            self.report,
            pod=pod,
            namespace=namespace
        )

    def _populate_storage_summary(self):
        """Generate storage summary data."""
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        report_table = getattr(self.accessor.report_schema, report_table_name)
        cluster_id = 'testcluster'
        for _ in range(25):
            pod = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
            namespace = ''.join(random.choice(string.ascii_lowercase) for _ in range(10))
            self.creator.create_ocp_usage_line_item(
                self.reporting_period, self.report, pod=pod, namespace=namespace
            )
            self.creator.create_ocp_storage_line_item(
                self.reporting_period, self.report, pod=pod, namespace=namespace
            )

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(
                Min('interval_start'), Max('interval_start')
            )
            start_date = report_entry['interval_start__min']
            end_date = report_entry['interval_start__max']

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        self.accessor.populate_line_item_daily_table(
            start_date, end_date, cluster_id
        )

        self.accessor.populate_storage_line_item_daily_table(
            start_date, end_date, cluster_id
        )
        self.accessor.populate_storage_line_item_daily_summary_table(
            start_date, end_date, cluster_id
        )

    def _populate_pod_summary(self):
        """Generate pod summary data."""
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        report_table = getattr(self.accessor.report_schema, report_table_name)

        cluster_id = 'testcluster'
        for _ in range(25):
            self.creator.create_ocp_usage_line_item(self.reporting_period, self.report)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(
                Min('interval_start'), Max('interval_start')
            )
            start_date = report_entry['interval_start__min']
            end_date = report_entry['interval_start__max']

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        self.accessor.populate_line_item_daily_table(start_date, end_date, cluster_id)
        self.accessor.populate_line_item_daily_summary_table(
            start_date, end_date, cluster_id
        )

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
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        columns = list(self.column_map[table_name].values())

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
        period_start = DateAccessor().today_with_timezone('UTC').replace(day=1)
        prev_period_start = period_start - relativedelta.relativedelta(months=1)
        reporting_period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid,
            period_date=period_start
        )
        prev_reporting_period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid,
            period_date=prev_period_start
        )

        with schema_context(self.schema):
            periods = self.accessor.get_usage_periods_by_date(period_start.date())
            self.assertIn(reporting_period, periods)
            periods = self.accessor.get_usage_periods_by_date(prev_period_start.date())
            self.assertIn(prev_reporting_period, periods)

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
        line_item_query = self.accessor.get_lineitem_query_for_reportid(report_id)
        with schema_context(self.schema):
            self.assertEqual(line_item_query.count(), 1)
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
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        daily_table_name = OCP_REPORT_TABLE_MAP['line_item_daily']

        report_table = getattr(self.accessor.report_schema, report_table_name)
        daily_table = getattr(self.accessor.report_schema, daily_table_name)

        for _ in range(25):
            self.creator.create_ocp_usage_line_item(self.reporting_period, self.report)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(
                Min('interval_start'), Max('interval_start')
            )
            start_date = report_entry['interval_start__min']
            end_date = report_entry['interval_start__max']

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(daily_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_line_item_daily_table(
            start_date, end_date, self.cluster_id
        )

        self.assertNotEqual(query.count(), initial_count)

        with schema_context(self.schema):
            daily_entry = daily_table.objects.all().aggregate(
                Min('usage_start'), Max('usage_start')
            )
            result_start_date = daily_entry['usage_start__min']
            result_end_date = daily_entry['usage_start__max']

        self.assertEqual(result_start_date, start_date)
        self.assertEqual(result_end_date, end_date)

        with schema_context(self.schema):
            entry = query.first()

            summary_columns = [
                'cluster_id',
                'namespace',
                'node',
                'node_capacity_cpu_core_seconds',
                'node_capacity_cpu_cores',
                'node_capacity_memory_byte_seconds',
                'node_capacity_memory_bytes',
                'pod',
                'pod_labels',
                'pod_limit_cpu_core_seconds',
                'pod_limit_memory_byte_seconds',
                'pod_request_cpu_core_seconds',
                'pod_request_memory_byte_seconds',
                'pod_usage_cpu_core_seconds',
                'pod_usage_memory_byte_seconds',
                'total_seconds',
                'usage_end',
                'usage_start',
            ]

            for column in summary_columns:
                self.assertIsNotNone(getattr(entry, column))

    def test_populate_line_item_daily_summary_table(self):
        """Test that the line item daily summary table populates."""
        self.tearDown()
        self.reporting_period = self.creator.create_ocp_report_period(
            provider_uuid=self.ocp_provider_uuid, cluster_id=self.cluster_id
        )
        self.report = self.creator.create_ocp_report(self.reporting_period)
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        summary_table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        report_table = getattr(self.accessor.report_schema, report_table_name)
        summary_table = getattr(self.accessor.report_schema, summary_table_name)

        for _ in range(25):
            self.creator.create_ocp_usage_line_item(self.reporting_period, self.report)
        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(
                Min('interval_start'), Max('interval_start')
            )
            start_date = report_entry['interval_start__min']
            end_date = report_entry['interval_start__max']

            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

            query = self.accessor._get_db_obj_query(summary_table_name)
            initial_count = query.count()

            self.accessor.populate_line_item_daily_table(
                start_date, end_date, self.cluster_id
            )
            self.accessor.populate_line_item_daily_summary_table(
                start_date, end_date, self.cluster_id
            )

            self.assertNotEqual(query.count(), initial_count)

            summary_entry = summary_table.objects.all().aggregate(
                Min('usage_start'), Max('usage_start')
            )
            result_start_date = summary_entry['usage_start__min']
            result_end_date = summary_entry['usage_start__max']

            self.assertEqual(result_start_date, start_date)
            self.assertEqual(result_end_date, end_date)

            entry = query.first()

        summary_columns = [
            'cluster_id',
            'namespace',
            'node',
            'node_capacity_cpu_core_hours',
            'node_capacity_cpu_cores',
            'node_capacity_memory_gigabyte_hours',
            'node_capacity_memory_gigabytes',
            'pod',
            'pod_labels',
            'pod_limit_cpu_core_hours',
            'pod_limit_memory_gigabyte_hours',
            'pod_request_cpu_core_hours',
            'pod_request_memory_gigabyte_hours',
            'pod_usage_cpu_core_hours',
            'pod_usage_memory_gigabyte_hours',
            'usage_end',
            'usage_start',
        ]

        for column in summary_columns:
            self.assertIsNotNone(getattr(entry, column))

    def test_populate_pod_label_summary_table(self):
        """Test that the pod label summary table is populated."""
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        agg_table_name = OCP_REPORT_TABLE_MAP['pod_label_summary']

        report_table = getattr(self.accessor.report_schema, report_table_name)

        today = DateAccessor().today_with_timezone('UTC')
        last_month = today - relativedelta.relativedelta(months=1)

        for start_date in (today, last_month):
            period = self.creator.create_ocp_report_period(
                self.ocp_provider_uuid,
                period_date=start_date
            )
            period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid,
            period_date=start_date
        )
            report = self.creator.create_ocp_report(period, start_date)
            self.creator.create_ocp_usage_line_item(period, report)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(
                Min('interval_start'), Max('interval_start')
            )
            start_date = report_entry['interval_start__min']
            end_date = report_entry['interval_start__max']

        query = self.accessor._get_db_obj_query(agg_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_line_item_daily_table(
            start_date, end_date, self.cluster_id
        )
        self.accessor.populate_pod_label_summary_table()

        self.assertNotEqual(query.count(), initial_count)

        with schema_context(self.schema):
            tags = query.all()
            tag_keys = [tag.key for tag in tags]

            with self.accessor._conn.cursor() as cursor:
                cursor.execute(
                    """SELECT DISTINCT jsonb_object_keys(pod_labels)
                        FROM reporting_ocpusagelineitem_daily"""
                )

                expected_tag_keys = cursor.fetchall()
                expected_tag_keys = [tag[0] for tag in expected_tag_keys]

            self.assertEqual(sorted(tag_keys), sorted(expected_tag_keys))

    def test_populate_volume_claim_label_summary_table(self):
        """Test that the volume claim summary table is populated."""
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        agg_table_name = OCP_REPORT_TABLE_MAP['volume_claim_label_summary']

        report_table = getattr(self.accessor.report_schema, report_table_name)

        today = DateAccessor().today_with_timezone('UTC')
        last_month = today - relativedelta.relativedelta(months=1)

        for start_date in (today, last_month):
            period = self.creator.create_ocp_report_period(
                self.ocp_provider_uuid,
                period_date=start_date
            )
            report = self.creator.create_ocp_report(period, start_date)
            self.creator.create_ocp_storage_line_item(period, report)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(
                Min('interval_start'), Max('interval_start')
            )
            start_date = report_entry['interval_start__min']
            end_date = report_entry['interval_start__max']

        query = self.accessor._get_db_obj_query(agg_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_storage_line_item_daily_table(
            start_date, end_date, self.cluster_id
        )
        self.accessor.populate_volume_claim_label_summary_table()

        self.assertNotEqual(query.count(), initial_count)

        with schema_context(self.schema):
            tags = query.all()
            tag_keys = [tag.key for tag in tags]

        with self.accessor._conn.cursor() as cursor:
            cursor.execute(
            """SELECT DISTINCT jsonb_object_keys(persistentvolumeclaim_labels)
                FROM reporting_ocpstoragelineitem_daily"""
            )
            expected_tag_keys = cursor.fetchall()
            expected_tag_keys = [tag[0] for tag in expected_tag_keys]

        self.assertEqual(sorted(tag_keys), sorted(expected_tag_keys))

    def test_populate_volume_label_summary_table(self):
        """Test that the volume label summary table is populated."""
        report_table_name = OCP_REPORT_TABLE_MAP['report']
        agg_table_name = OCP_REPORT_TABLE_MAP['volume_label_summary']

        report_table = getattr(self.accessor.report_schema, report_table_name)

        today = DateAccessor().today_with_timezone('UTC')
        last_month = today - relativedelta.relativedelta(months=1)

        for start_date in (today, last_month):
            period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid,
            period_date=start_date
        )
            report = self.creator.create_ocp_report(period, start_date)
            self.creator.create_ocp_storage_line_item(period, report)
        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(
                Min('interval_start'), Max('interval_start')
            )
            start_date = report_entry['interval_start__min']
            end_date = report_entry['interval_start__max']

        query = self.accessor._get_db_obj_query(agg_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_storage_line_item_daily_table(
            start_date, end_date, self.cluster_id
        )
        self.accessor.populate_volume_label_summary_table()

        self.assertNotEqual(query.count(), initial_count)

        with schema_context(self.schema):
            tags = query.all()
            tag_keys = [tag.key for tag in tags]

        with self.accessor._conn.cursor() as cursor:
            cursor.execute(
                """SELECT DISTINCT jsonb_object_keys(persistentvolume_labels)
                    FROM reporting_ocpstoragelineitem_daily"""
            )

            expected_tag_keys = cursor.fetchall()
            expected_tag_keys = [tag[0] for tag in expected_tag_keys]

        self.assertEqual(sorted(tag_keys), sorted(expected_tag_keys))

    def test_get_usage_period_before_date(self):
        """Test that gets a query for usage report periods before a date."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        query = self.accessor._get_db_obj_query(table_name)
        with schema_context(self.schema):
            first_entry = query.first()

            # Verify that the result is returned for cutoff_date == report_period_start
            cutoff_date = first_entry.report_period_start
            usage_period = self.accessor.get_usage_period_before_date(cutoff_date)
            self.assertEqual(usage_period.count(), 1)
            self.assertEqual(usage_period.first().report_period_start, cutoff_date)

            # Verify that the result is returned for a date later than cutoff_date
            later_date = cutoff_date + relativedelta.relativedelta(months=+1)
            later_cutoff = later_date.replace(month=later_date.month, day=15)
            usage_period = self.accessor.get_usage_period_before_date(later_cutoff)
            self.assertEqual(usage_period.count(), 1)
            self.assertEqual(usage_period.first().report_period_start, cutoff_date)

            # Verify that no results are returned for a date earlier than cutoff_date
            earlier_date = cutoff_date + relativedelta.relativedelta(months=-1)
            earlier_cutoff = earlier_date.replace(month=earlier_date.month, day=15)
            usage_period = self.accessor.get_usage_period_before_date(earlier_cutoff)
            self.assertEqual(usage_period.count(), 0)

    def test_get_item_query_report_period_id(self):
        """Test that gets a usage report line item query given a report period id."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']

        with schema_context(self.schema):
            # Verify that the line items for the test report_period_id are returned
            report_period_id = self.accessor._get_db_obj_query(table_name).first().id
        line_item_query = self.accessor.get_item_query_report_period_id(
            report_period_id
        )
        with schema_context(self.schema):
            self.assertEqual(line_item_query.count(), 1)
            self.assertEqual(line_item_query.first().report_period_id, report_period_id)

            # Verify that no line items are returned for a missing report_period_id
            wrong_report_period_id = report_period_id + 1
        line_item_query = self.accessor.get_item_query_report_period_id(
            wrong_report_period_id
        )
        with schema_context(self.schema):
            self.assertEqual(line_item_query.count(), 0)

    def test_get_report_query_report_period_id(self):
        """Test that gets a usage report item query given a report period id."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']

        with schema_context(self.schema):
            # Verify that the line items for the test report_period_id are returned
            report_period_id = self.accessor._get_db_obj_query(table_name).first().id
        usage_report_query = self.accessor.get_report_query_report_period_id(
            report_period_id
        )
        with schema_context(self.schema):
            self.assertEqual(usage_report_query.count(), 1)
            self.assertEqual(usage_report_query.first().report_period_id, report_period_id)

            # Verify that no line items are returned for a missing report_period_id
            wrong_report_period_id = report_period_id + 1
        usage_report_query = self.accessor.get_report_query_report_period_id(
            wrong_report_period_id
        )
        with schema_context(self.schema):
            self.assertEqual(usage_report_query.count(), 0)

    def test_get_pod_cpu_core_hours(self):
        """Test that gets pod cpu usage/request."""
        self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        # Verify that the line items for the test cluster_id are returned
        cluster_id = self.accessor._get_db_obj_query(table_name).first().cluster_id
        reports = self.accessor._get_db_obj_query(table_name).filter(
            cluster_id=cluster_id
        )

        expected_usage_reports = {
            entry.id: entry.pod_usage_cpu_core_hours for entry in reports
        }
        expected_request_reports = {
            entry.id: entry.pod_usage_cpu_core_hours for entry in reports
        }
        cpu_usage_query = self.accessor.get_pod_usage_cpu_core_hours(cluster_id)
        cpu_request_query = self.accessor.get_pod_request_cpu_core_hours(cluster_id)

        self.assertEqual(
            len(cpu_usage_query.keys()), len(expected_usage_reports.keys())
        )
        self.assertEqual(
            len(cpu_request_query.keys()), len(expected_request_reports.keys())
        )

        # Verify that no line items are returned for an incorrect cluster_id
        wrong_cluster_id = cluster_id + 'bad'
        cpu_usage_query = self.accessor.get_pod_usage_cpu_core_hours(wrong_cluster_id)
        self.assertEqual(len(cpu_usage_query.keys()), 0)
        cpu_request_query = self.accessor.get_pod_request_cpu_core_hours(
            wrong_cluster_id
        )
        self.assertEqual(len(cpu_request_query.keys()), 0)


    def test_get_pod_cpu_core_hours_no_cluster_id(self):
        """Test that gets pod cpu usage/request without cluster id."""
        self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        # Verify that the line items for the test cluster_id are returned
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source='Pod').all()

        expected_usage_reports = {
            entry.id: entry.pod_usage_cpu_core_hours for entry in reports
        }
        expected_request_reports = {
            entry.id: entry.pod_usage_cpu_core_hours for entry in reports
        }
        cpu_usage_query = self.accessor.get_pod_usage_cpu_core_hours()
        cpu_request_query = self.accessor.get_pod_request_cpu_core_hours()

        self.assertEqual(
            len(cpu_usage_query.keys()), len(expected_usage_reports.keys())
        )
        self.assertEqual(
            len(cpu_request_query.keys()), len(expected_request_reports.keys())
        )

    def test_get_pod_memory_gigabyte_hours(self):
        """Test that gets pod memory usage/request."""
        self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        # Verify that the line items for the test cluster_id are returned
        cluster_id = self.accessor._get_db_obj_query(table_name).first().cluster_id
        reports = self.accessor._get_db_obj_query(table_name).filter(
            cluster_id=cluster_id
        )

        expected_usage_reports = {
            entry.id: entry.pod_usage_memory_gigabyte_hours for entry in reports
        }
        expected_request_reports = {
            entry.id: entry.pod_request_memory_gigabyte_hours for entry in reports
        }
        mem_usage_query = self.accessor.get_pod_usage_memory_gigabyte_hours(cluster_id)
        mem_request_query = self.accessor.get_pod_request_memory_gigabyte_hours(
            cluster_id
        )

        self.assertEqual(
            len(mem_usage_query.keys()), len(expected_usage_reports.keys())
        )
        self.assertEqual(
            len(mem_request_query.keys()), len(expected_request_reports.keys())
        )

        # Verify that no line items are returned for an incorrect cluster_id
        wrong_cluster_id = cluster_id + 'bad'
        mem_usage_query = self.accessor.get_pod_usage_cpu_core_hours(wrong_cluster_id)
        self.assertEqual(len(mem_usage_query.keys()), 0)
        mem_request_query = self.accessor.get_pod_usage_cpu_core_hours(wrong_cluster_id)
        self.assertEqual(len(mem_request_query.keys()), 0)

    def test_get_pod_memory_gigabyte_hours_no_cluster_id(self):
        """Test that gets pod memory usage/request without cluster id."""
        self._populate_pod_summary()
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        # Verify that the line items for the test cluster_id are returned
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source='Pod').all()

        expected_usage_reports = {
            entry.id: entry.pod_usage_memory_gigabyte_hours for entry in reports
        }
        expected_request_reports = {
            entry.id: entry.pod_request_memory_gigabyte_hours for entry in reports
        }
        mem_usage_query = self.accessor.get_pod_usage_memory_gigabyte_hours()
        mem_request_query = self.accessor.get_pod_request_memory_gigabyte_hours()

        self.assertEqual(
            len(mem_usage_query.keys()), len(expected_usage_reports.keys())
        )
        self.assertEqual(
            len(mem_request_query.keys()), len(expected_request_reports.keys())
        )

    def test_get_volume_gigabyte_months(self):
        """Test that gets pod volume usage/request."""
        self._populate_storage_summary()
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        # Verify that the line items for the test cluster_id are returned
        reports = self.accessor._get_db_obj_query(table_name).filter(
            cluster_id=self.cluster_id,
            data_source='Storage'
        )

        expected_usage_reports = {
            entry.id: entry.persistentvolumeclaim_usage_gigabyte_months
            for entry in reports
        }
        expected_request_reports = {
            entry.id: entry.volume_request_storage_gigabyte_months for entry in reports
        }
        vol_usage_query = self.accessor.get_persistentvolumeclaim_usage_gigabyte_months(
            self.cluster_id
        )
        vol_request_query = self.accessor.get_volume_request_storage_gigabyte_months(
            self.cluster_id
        )

        self.assertEqual(
            len(vol_usage_query.keys()), len(expected_usage_reports.keys())
        )
        self.assertEqual(
            len(vol_request_query.keys()), len(expected_request_reports.keys())
        )

        # Verify that no line items are returned for an incorrect cluster_id
        wrong_cluster_id = self.cluster_id + 'bad'
        vol_usage_query = self.accessor.get_persistentvolumeclaim_usage_gigabyte_months(
            wrong_cluster_id
        )
        self.assertEqual(len(vol_usage_query.keys()), 0)
        vol_request_query = self.accessor.get_volume_request_storage_gigabyte_months(
            wrong_cluster_id
        )
        self.assertEqual(len(vol_request_query.keys()), 0)

    def test_get_volume_gigabyte_months_no_cluster_id(self):
        """Test that gets pod volume usage/request without cluster id."""
        self._populate_storage_summary()
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        # Verify that the line items for the test cluster_id are returned
        reports = self.accessor._get_db_obj_query(table_name).filter(data_source='Storage').all()

        expected_usage_reports = {
            entry.id: entry.persistentvolumeclaim_usage_gigabyte_months
            for entry in reports
        }
        expected_request_reports = {
            entry.id: entry.volume_request_storage_gigabyte_months for entry in reports
        }
        vol_usage_query = (
            self.accessor.get_persistentvolumeclaim_usage_gigabyte_months()
        )
        vol_request_query = self.accessor.get_volume_request_storage_gigabyte_months()

        self.assertEqual(
            len(vol_usage_query.keys()), len(expected_usage_reports.keys())
        )
        self.assertEqual(
            len(vol_request_query.keys()), len(expected_request_reports.keys())
        )

    def test_get_daily_usage_query_for_clusterid(self):
        """Test that daily usage getter is correct."""
        self._populate_pod_summary()
        daily_usage = self.accessor.get_daily_usage_query_for_clusterid(self.cluster_id)
        self.assertEquals(daily_usage.count(), 26)

    def test_get_summary_usage_query_for_clusterid(self):
        """Test that daily usage summary getter is correct."""
        daily_usage_summary = self.accessor.get_summary_usage_query_for_clusterid(
            self.cluster_id
        )
        with schema_context(self.schema):
            self.assertEquals(daily_usage_summary.count(), 0)
        self._populate_pod_summary()
        with schema_context(self.schema):
            self.assertEquals(daily_usage_summary.count(), 26)

    def test_get_storage_item_query_report_period_id(self):
        """Test that get_storage_item_query_report_period_id is correct."""
        storage_line_item = self.accessor.get_storage_item_query_report_period_id(
            self.reporting_period.id
        )
        with schema_context(self.schema):
            self.assertEquals(storage_line_item.count(), 1)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEquals(storage_line_item.count(), 26)

    def test_get_daily_storage_item_query_cluster_id(self):
        """Test that get_daily_storage_item_query_cluster_id is correct."""
        with schema_context(self.schema):
            storage_line_item = self.accessor.get_daily_storage_item_query_cluster_id(
                self.cluster_id
            )
            self.assertEquals(storage_line_item.count(), 0)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEquals(storage_line_item.count(), 26)

    def test_get_storage_summary_query_cluster_id(self):
        """Test that get_storage_summary_query_cluster_id is correct."""
        storage_summary = self.accessor.get_storage_summary_query_cluster_id(
            self.cluster_id
        )
        with schema_context(self.schema):
            self.assertEquals(storage_summary.count(), 0)
        self._populate_storage_summary()
        with schema_context(self.schema):
            self.assertEquals(storage_summary.count(), 26)

    def test_get_report_periods(self):
        """Test that report_periods getter is correct."""
        periods = self.accessor.get_report_periods()
        self.assertEquals(len(periods), 1)

    def test_get_reports(self):
        """Test that the report getter is correct."""
        periods = self.accessor.get_reports()
        self.assertEquals(len(periods), 1)

    def test_populate_monthly_cost(self):
        """Test that the monthly cost row in the summary table is populated."""
        report_table_name = OCP_REPORT_TABLE_MAP['report']

        report_table = getattr(self.accessor.report_schema, report_table_name)

        node_cost = random.randrange(1, 100)
        for _ in range(5):
            self.creator.create_ocp_usage_line_item(self.reporting_period, self.report)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(
                Min('interval_start'), Max('interval_start')
            )
            start_date = report_entry['interval_start__min']
            end_date = report_entry['interval_start__max']

            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

            self.accessor.populate_line_item_daily_table(start_date, end_date, self.cluster_id)

            self.accessor.populate_line_item_daily_summary_table(
                start_date, end_date, self.cluster_id
            )

            self.accessor.populate_monthly_cost(node_cost=node_cost, start_date=str(start_date))

            first_month, first_next_month = month_date_range_tuple(start_date)

            monthly_cost_row = OCPUsageLineItemDailySummary.objects.filter(
                usage_start=first_month,
                monthly_cost__isnull=False
            ).first()

            self.assertEquals(monthly_cost_row.monthly_cost, 6*node_cost)
