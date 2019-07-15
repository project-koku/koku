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

"""Test the download task."""

import shutil
import tempfile
import logging
import os
from datetime import date, datetime, timedelta
from unittest.mock import call, patch, Mock, ANY

import faker
from dateutil import relativedelta
from sqlalchemy.sql import func

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP, OCP_REPORT_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.provider_status_accessor import ProviderStatusCode
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.external.report_downloader import ReportDownloader, ReportDownloaderError
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.report_processor import ReportProcessorError
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor.tasks import (
    get_report_files,
    summarize_reports,
    remove_expired_data,
    update_charge_info,
    update_all_summary_tables,
    update_summary_tables,
)
from tests import MasuTestCase
from tests.database.helpers import ReportObjectCreator
from tests.external.downloader.aws import fake_arn


class FakeDownloader(Mock):
    def get_reports(self):
        fake_file_list = [
            '/var/tmp/masu/my-report-name/aws/my-report-file.csv',
            '/var/tmp/masu/other-report-name/aws/other-report-file.csv',
        ]
        return fake_file_list


class GetReportFileTests(MasuTestCase):
    """Test Cases for the celery task."""

    fake = faker.Faker()

    @patch(
        'masu.processor._tasks.download.ReportDownloader', return_value=FakeDownloader
    )
    def test_get_report(self, fake_downloader):
        """Test task"""
        account = fake_arn(service='iam', generate_account_id=True)
        report = _get_report_files(
            customer_name=self.fake.word(),
            authentication=account,
            provider_type='AWS',
            report_name=self.fake.word(),
            provider_uuid=self.aws_test_provider_uuid,
            billing_source=self.fake.word(),
        )

        self.assertIsInstance(report, list)
        self.assertGreater(len(report), 0)

    @patch(
        'masu.processor._tasks.download.ReportDownloader', return_value=FakeDownloader
    )
    def test_disk_status_logging(self, fake_downloader):
        """Test task for logging when temp directory exists."""
        logging.disable(logging.NOTSET)
        os.makedirs(Config.TMP_DIR, exist_ok=True)

        account = fake_arn(service='iam', generate_account_id=True)
        expected = 'INFO:masu.processor._tasks.download:Available disk space'
        with self.assertLogs('masu.processor._tasks.download', level='INFO') as logger:
            _get_report_files(
                customer_name=self.fake.word(),
                authentication=account,
                provider_type='AWS',
                report_name=self.fake.word(),
                provider_uuid=self.aws_test_provider_uuid,
                billing_source=self.fake.word(),
            )
            statement_found = False
            for log in logger.output:
                if expected in log:
                    statement_found = True
            self.assertTrue(statement_found)

        shutil.rmtree(Config.TMP_DIR, ignore_errors=True)

    @patch(
        'masu.processor._tasks.download.ReportDownloader', return_value=FakeDownloader
    )
    def test_disk_status_logging_no_dir(self, fake_downloader):
        """Test task for logging when temp directory does not exist."""
        logging.disable(logging.NOTSET)

        Config.TMP_DIR = '/this/path/does/not/exist'

        account = fake_arn(service='iam', generate_account_id=True)
        expected = (
            'INFO:masu.processor._tasks.download:Unable to find'
            + f' available disk space. {Config.TMP_DIR} does not exist'
        )
        with self.assertLogs('masu.processor._tasks.download', level='INFO') as logger:
            _get_report_files(
                customer_name=self.fake.word(),
                authentication=account,
                provider_type='AWS',
                report_name=self.fake.word(),
                provider_uuid=self.aws_test_provider_uuid,
                billing_source=self.fake.word(),
            )
            self.assertIn(expected, logger.output)

    @patch(
        'masu.processor._tasks.download.ReportDownloader._set_downloader',
        side_effect=Exception('only a test'),
    )
    def test_get_report_exception(self, fake_downloader):
        """Test task"""
        account = fake_arn(service='iam', generate_account_id=True)

        with self.assertRaises(Exception):
            _get_report_files(
                customer_name=self.fake.word(),
                authentication=account,
                provider_type='AWS',
                report_name=self.fake.word(),
                provider_uuid=self.aws_test_provider_uuid,
                billing_source=self.fake.word(),
            )

    @patch(
        'masu.processor._tasks.download.ReportDownloader._set_downloader',
        return_value=FakeDownloader,
    )
    @patch(
        'masu.database.provider_db_accessor.ProviderDBAccessor.get_setup_complete',
        return_value=True,
    )
    def test_get_report_with_override(self, fake_accessor, fake_report_files):
        """Test _get_report_files on non-initial load with override set."""
        Config.INGEST_OVERRIDE = True
        Config.INITIAL_INGEST_NUM_MONTHS = 5
        initial_month_qty = Config.INITIAL_INGEST_NUM_MONTHS

        account = fake_arn(service='iam', generate_account_id=True)
        with patch.object(ReportDownloader, 'get_reports') as download_call:
            _get_report_files(
                customer_name=self.fake.word(),
                authentication=account,
                provider_type='AWS',
                report_name=self.fake.word(),
                provider_uuid=self.aws_test_provider_uuid,
                billing_source=self.fake.word(),
            )

            download_call.assert_called_with(initial_month_qty)

        Config.INGEST_OVERRIDE = False
        Config.INITIAL_INGEST_NUM_MONTHS = 2

    @patch('masu.processor._tasks.download.ProviderStatus.set_error')
    @patch(
        'masu.processor._tasks.download.ReportDownloader._set_downloader',
        side_effect=ReportDownloaderError('only a test'),
    )
    def test_get_report_exception_update_status(self, fake_downloader, fake_status):
        """Test that status is updated when an exception is raised."""
        account = fake_arn(service='iam', generate_account_id=True)

        try:
            _get_report_files(
                customer_name=self.fake.word(),
                authentication=account,
                provider_type='AWS',
                report_name=self.fake.word(),
                provider_uuid=self.aws_test_provider_uuid,
                billing_source=self.fake.word(),
            )
        except ReportDownloaderError:
            pass
        fake_status.assert_called()

    @patch('masu.processor._tasks.download.ProviderStatus.set_status')
    @patch('masu.processor._tasks.download.ReportDownloader', spec=True)
    def test_get_report_update_status(self, fake_downloader, fake_status):
        """Test that status is updated when downloading is complete."""
        account = fake_arn(service='iam', generate_account_id=True)

        _get_report_files(
            customer_name=self.fake.word(),
            authentication=account,
            provider_type='AWS',
            report_name=self.fake.word(),
            provider_uuid=self.aws_test_provider_uuid,
            billing_source=self.fake.word(),
        )
        fake_status.assert_called_with(ProviderStatusCode.READY)


class ProcessReportFileTests(MasuTestCase):
    """Test Cases for the Orchestrator object."""

    @patch('masu.processor._tasks.process.ReportProcessor')
    @patch('masu.processor._tasks.process.ReportStatsDBAccessor')
    @patch('masu.processor._tasks.process.ReportManifestDBAccessor')
    def test_process_file(
        self, mock_manifest_accessor, mock_stats_accessor, mock_processor
    ):
        """Test the process_report_file functionality."""
        report_dir = tempfile.mkdtemp()
        path = '{}/{}'.format(report_dir, 'file1.csv')
        schema_name = self.test_schema
        provider = 'AWS'
        provider_uuid = self.aws_test_provider_uuid
        report_dict = {
            'file': path,
            'compression': 'gzip',
            'start_date': str(DateAccessor().today()),
        }

        mock_proc = mock_processor()
        mock_stats_acc = mock_stats_accessor().__enter__()
        mock_manifest_acc = mock_manifest_accessor().__enter__()

        _process_report_file(schema_name, provider, provider_uuid, report_dict)

        mock_proc.process.assert_called()
        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_called()
        mock_stats_acc.commit.assert_called()
        mock_manifest_acc.mark_manifest_as_updated.assert_called()
        shutil.rmtree(report_dir)

    @patch('masu.processor._tasks.process.ReportProcessor')
    @patch('masu.processor._tasks.process.ReportStatsDBAccessor')
    def test_process_file_exception(self, mock_stats_accessor, mock_processor):
        """Test the process_report_file functionality when exception is thrown."""
        report_dir = tempfile.mkdtemp()
        path = '{}/{}'.format(report_dir, 'file1.csv')
        schema_name = self.test_schema
        provider = 'AWS'
        provider_uuid = self.aws_test_provider_uuid
        report_dict = {
            'file': path,
            'compression': 'gzip',
            'start_date': str(DateAccessor().today()),
        }

        mock_processor.side_effect = ReportProcessorError('mock error')
        mock_stats_acc = mock_stats_accessor().__enter__()

        with self.assertRaises(ReportProcessorError):
            _process_report_file(schema_name, provider, provider_uuid, report_dict)

        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_not_called()
        mock_stats_acc.commit.assert_called()
        shutil.rmtree(report_dir)

    @patch('masu.processor._tasks.process.ReportProcessor')
    @patch('masu.processor._tasks.process.ReportStatsDBAccessor')
    @patch('masu.database.report_manifest_db_accessor.ReportManifestDBAccessor')
    def test_process_file_missing_manifest(
        self, mock_manifest_accessor, mock_stats_accessor, mock_processor
    ):
        """Test the process_report_file functionality when manifest is missing."""
        mock_manifest_accessor.get_manifest_by_id.return_value = None
        report_dir = tempfile.mkdtemp()
        path = '{}/{}'.format(report_dir, 'file1.csv')
        schema_name = self.test_schema
        provider = 'AWS'
        provider_uuid = self.aws_test_provider_uuid
        report_dict = {
            'file': path,
            'compression': 'gzip',
            'start_date': str(DateAccessor().today()),
        }

        mock_proc = mock_processor()
        mock_stats_acc = mock_stats_accessor().__enter__()
        mock_manifest_acc = mock_manifest_accessor().__enter__()

        _process_report_file(schema_name, provider, provider_uuid, report_dict)

        mock_proc.process.assert_called()
        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_called()
        mock_stats_acc.commit.assert_called()
        mock_manifest_acc.mark_manifest_as_updated.assert_not_called()
        shutil.rmtree(report_dir)

    @patch('masu.processor.tasks.update_summary_tables')
    def test_summarize_reports_empty_list(self, mock_update_summary):
        """
        Test that the summarize_reports task is called when empty processing list is provided.
        """
        mock_update_summary.delay = Mock()

        summarize_reports([])
        mock_update_summary.delay.assert_not_called()

    @patch('masu.processor.tasks.update_summary_tables')
    def test_summarize_reports_processing_list(self, mock_update_summary):
        """
        Test that the summarize_reports task is called when a processing list is provided.
        """
        mock_update_summary.delay = Mock()

        report_meta = {}
        report_meta['start_date'] = str(DateAccessor().today())
        report_meta['schema_name'] = self.test_schema
        report_meta['provider_type'] = 'OCP'
        report_meta['provider_uuid'] = self.ocp_test_provider_uuid
        report_meta['manifest_id'] = 1
        reports_to_summarize = [report_meta]

        summarize_reports(reports_to_summarize)
        mock_update_summary.delay.assert_called()


class TestProcessorTasks(MasuTestCase):
    """Test cases for Processor Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.fake = faker.Faker()
        cls.fake_reports = [
            {'file': cls.fake.word(), 'compression': 'GZIP'},
            {'file': cls.fake.word(), 'compression': 'PLAIN'},
        ]

        cls.fake_account = fake_arn(service='iam', generate_account_id=True)
        cls.today = DateAccessor().today_with_timezone('UTC')
        cls.yesterday = cls.today - timedelta(days=1)

    def setUp(self):
        super().setUp()

        self.fake_get_report_args = {
            'customer_name': self.fake.word(),
            'authentication': self.fake_account,
            'provider_type': 'AWS',
            'schema_name': self.fake.word(),
            'billing_source': self.fake.word(),
            'provider_uuid': self.aws_test_provider_uuid,
        }

    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime')
    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime')
    @patch('masu.processor.tasks._get_report_files')
    def test_get_report_files_timestamps_aligned(
        self, mock_get_files, mock_started, mock_completed
    ):
        """
        Test to return reports only when they have not been processed.
        """
        mock_get_files.return_value = self.fake_reports

        mock_started.return_value = self.yesterday
        mock_completed.return_value = self.today

        reports = get_report_files(**self.fake_get_report_args)
        self.assertEqual(reports, [])

    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime')
    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime')
    @patch('masu.processor.tasks._get_report_files')
    def test_get_report_files_timestamps_misaligned(
        self, mock_get_files, mock_started, mock_completed
    ):
        """
        Test to return reports with misaligned timestamps.
        """
        mock_get_files.return_value = self.fake_reports

        mock_started.return_value = self.today
        mock_completed.return_value = self.yesterday

        reports = get_report_files(**self.fake_get_report_args)
        self.assertEqual(reports, [])

    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime')
    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime')
    @patch('masu.processor.tasks._get_report_files')
    @patch('masu.processor.tasks._process_report_file')
    def test_get_report_files_timestamps_empty_start(
        self, mock_process_files, mock_get_files, mock_started, mock_completed
    ):
        """
        Test that the chained task is called when no start time is set.
        """
        mock_process_files.apply_async = Mock()
        mock_get_files.return_value = self.fake_reports

        mock_started.return_value = None
        mock_completed.return_value = self.today
        reports = get_report_files(**self.fake_get_report_args)
        self.assertIsNotNone(reports)

    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime')
    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime')
    @patch('masu.processor.tasks._get_report_files')
    @patch('masu.external.date_accessor.DateAccessor.today')
    def test_get_report_files_timestamps_empty_end(
        self, mock_date, mock_get_files, mock_started, mock_completed
    ):
        """
        Test that the chained task is not called when no end time is set since
        processing is in progress.
        """
        mock_get_files.return_value = self.fake_reports

        mock_started.return_value = self.today

        # Make sure today() is only an hour from get_last_started_datetime (within 2 hr timeout)
        mock_date.return_value = self.today + timedelta(hours=1)

        mock_completed.return_value = None
        reports = get_report_files(**self.fake_get_report_args)
        self.assertEqual(reports, [])

    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime')
    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime')
    @patch('masu.processor.tasks._get_report_files')
    @patch('masu.processor.tasks._process_report_file')
    @patch('masu.external.date_accessor.DateAccessor.today_with_timezone')
    def test_get_report_files_timestamps_empty_end_timeout(
        self,
        mock_date,
        mock_process_files,
        mock_get_files,
        mock_started,
        mock_completed,
    ):
        """
        Test that the chained task is called when no end time is set since
        processing has exceeded the timeout.
        """
        mock_process_files.apply_async = Mock()
        mock_get_files.return_value = self.fake_reports

        mock_started.return_value = self.today
        mock_completed.return_value = None

        mock_date.return_value = self.today + timedelta(hours=3)
        reports = get_report_files(**self.fake_get_report_args)
        self.assertIsNotNone(reports)

    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime')
    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime')
    @patch('masu.processor.tasks._get_report_files')
    @patch('masu.processor.tasks._process_report_file')
    @patch('masu.external.date_accessor.DateAccessor.today_with_timezone')
    def test_get_report_files_timestamps_empty_end_no_timeout(
        self,
        mock_date,
        mock_process_files,
        mock_get_files,
        mock_started,
        mock_completed,
    ):
        """
        Test that the chained task is not called when no end time is set since
        processing is in progress but completion timeout has not been reached.
        """
        mock_get_files.return_value = self.fake_reports

        mock_started.return_value = self.today
        mock_completed.return_value = None

        mock_date.return_value = self.today + timedelta(hours=1)

        reports = get_report_files(**self.fake_get_report_args)
        self.assertIsNotNone(reports)

    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime')
    @patch('masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime')
    @patch('masu.processor.tasks._get_report_files')
    @patch('masu.processor.tasks._process_report_file')
    def test_get_report_files_timestamps_empty_both(
        self, mock_process_file, mock_get_files, mock_started, mock_completed
    ):
        """
        Test that the chained task is called when no timestamps are set.
        """
        mock_get_files.return_value = self.fake_reports
        mock_process_file.return_value = None

        mock_started.return_value = None
        mock_completed.return_value = None
        reports = get_report_files(**self.fake_get_report_args)
        self.assertIsNotNone(reports)


class TestRemoveExpiredDataTasks(MasuTestCase):
    """Test cases for Processor Celery tasks."""

    @patch.object(ExpiredDataRemover, 'remove')
    def test_remove_expired_data(self, fake_remover):
        """Test task"""
        expected_results = [
            {
                'account_payer_id': '999999999',
                'billing_period_start': '2018-06-24 15:47:33.052509',
            }
        ]
        fake_remover.return_value = expected_results

        expected = 'INFO:masu.processor._tasks.remove_expired:Expired Data: {}'

        # disable logging override set in masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs('masu.processor._tasks.remove_expired') as logger:
            remove_expired_data(
                schema_name=self.test_schema, provider='AWS', simulate=True
            )
            self.assertIn(expected.format(str(expected_results)), logger.output)


class TestUpdateSummaryTablesTask(MasuTestCase):
    """Test cases for Processor summary table Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Setup for the class."""
        super().setUpClass()
        cls.aws_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.ocp_tables = list(OCP_REPORT_TABLE_MAP.values())
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values()) + list(
            OCP_REPORT_TABLE_MAP.values()
        )
        report_common_db = ReportingCommonDBAccessor()
        cls.column_map = report_common_db.column_map
        report_common_db.close_session()

    @classmethod
    def tearDownClass(cls):
        """Tear down the test class."""
        super().tearDownClass()

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.schema_name = self.test_schema
        self.aws_accessor = AWSReportDBAccessor(
            schema=self.schema_name, column_map=self.column_map
        )
        self.ocp_accessor = OCPReportDBAccessor(
            schema=self.schema_name, column_map=self.column_map
        )

        self.creator = ReportObjectCreator(
            self.aws_accessor,
            self.column_map,
            self.aws_accessor.report_schema.column_types,
        )

        # Populate some line item data so that the summary tables
        # have something to pull from
        self.start_date = DateAccessor().today_with_timezone('UTC').replace(day=1)
        last_month = self.start_date - relativedelta.relativedelta(months=1)

        for cost_entry_date in (self.start_date, last_month):
            bill = self.creator.create_cost_entry_bill(cost_entry_date)
            cost_entry = self.creator.create_cost_entry(bill, cost_entry_date)
            for family in [
                'Storage',
                'Compute Instance',
                'Database Storage',
                'Database Instance',
            ]:
                product = self.creator.create_cost_entry_product(family)
                pricing = self.creator.create_cost_entry_pricing()
                reservation = self.creator.create_cost_entry_reservation()
                self.creator.create_cost_entry_line_item(
                    bill, cost_entry, product, pricing, reservation
                )
        provider_ocp_uuid = self.ocp_test_provider_uuid

        with ProviderDBAccessor(provider_uuid=provider_ocp_uuid) as provider_accessor:
            provider_id = provider_accessor.get_provider().id

        cluster_id = self.ocp_provider_resource_name
        for period_date in (self.start_date, last_month):
            period = self.creator.create_ocp_report_period(
                period_date, provider_id=provider_id, cluster_id=cluster_id
            )
            report = self.creator.create_ocp_report(period, period_date)
            for _ in range(25):
                self.creator.create_ocp_usage_line_item(period, report)

    def tearDown(self):
        """Return the database to a pre-test state."""
        for table_name in self.aws_tables:
            tables = self.aws_accessor._get_db_obj_query(table_name).all()
            for table in tables:
                self.aws_accessor._session.delete(table)
        self.aws_accessor.commit()
        for table_name in self.ocp_tables:
            tables = self.ocp_accessor._get_db_obj_query(table_name).all()
            for table in tables:
                self.ocp_accessor._session.delete(table)
        self.ocp_accessor.commit()

        self.aws_accessor._session.rollback()
        self.aws_accessor.close_connections()
        self.aws_accessor.close_session()
        self.ocp_accessor.close_connections()
        self.ocp_accessor.close_session()
        super().tearDown()

    @patch('masu.processor.tasks.update_charge_info')
    def test_update_summary_tables_aws(self, mock_charge_info):
        """Test that the summary table task runs."""
        provider = 'AWS'
        provider_aws_uuid = self.aws_test_provider_uuid

        daily_table_name = AWS_CUR_TABLE_MAP['line_item_daily']
        summary_table_name = AWS_CUR_TABLE_MAP['line_item_daily_summary']
        start_date = self.start_date.replace(day=1) + relativedelta.relativedelta(
            months=-1
        )

        daily_query = self.aws_accessor._get_db_obj_query(daily_table_name)
        summary_query = self.aws_accessor._get_db_obj_query(summary_table_name)

        initial_daily_count = daily_query.count()
        initial_summary_count = summary_query.count()

        self.assertEqual(initial_daily_count, 0)
        self.assertEqual(initial_summary_count, 0)

        update_summary_tables(self.schema_name, provider, provider_aws_uuid, start_date)

        self.assertNotEqual(daily_query.count(), initial_daily_count)
        self.assertNotEqual(summary_query.count(), initial_summary_count)

    @patch('masu.processor.tasks.update_charge_info')
    def test_update_summary_tables_aws_end_date(self, mock_charge_info):
        """Test that the summary table task respects a date range."""
        provider = 'AWS'
        provider_aws_uuid = self.aws_test_provider_uuid
        ce_table_name = AWS_CUR_TABLE_MAP['cost_entry']
        daily_table_name = AWS_CUR_TABLE_MAP['line_item_daily']
        summary_table_name = AWS_CUR_TABLE_MAP['line_item_daily_summary']

        start_date = self.start_date.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) + relativedelta.relativedelta(months=-1)

        end_date = start_date + timedelta(days=10)
        end_date = end_date.replace(hour=23, minute=59, second=59)

        daily_table = getattr(self.aws_accessor.report_schema, daily_table_name)
        summary_table = getattr(self.aws_accessor.report_schema, summary_table_name)
        ce_table = getattr(self.aws_accessor.report_schema, ce_table_name)

        ce_start_date = (
            self.aws_accessor._session.query(func.min(ce_table.interval_start))
            .filter(ce_table.interval_start >= start_date)
            .first()[0]
        )

        ce_end_date = (
            self.aws_accessor._session.query(func.max(ce_table.interval_start))
            .filter(ce_table.interval_start <= end_date)
            .first()[0]
        )

        # The summary tables will only include dates where there is data
        expected_start_date = max(start_date, ce_start_date)
        expected_start_date = expected_start_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        expected_end_date = min(end_date, ce_end_date)
        expected_end_date = expected_end_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        update_summary_tables(
            self.schema_name, provider, provider_aws_uuid, start_date, end_date
        )

        result_start_date, result_end_date = self.aws_accessor._session.query(
            func.min(daily_table.usage_start), func.max(daily_table.usage_end)
        ).first()

        self.assertEqual(result_start_date, expected_start_date)
        self.assertEqual(result_end_date, expected_end_date)

        result_start_date, result_end_date = self.aws_accessor._session.query(
            func.min(summary_table.usage_start), func.max(summary_table.usage_end)
        ).first()

        self.assertEqual(result_start_date, expected_start_date)
        self.assertEqual(result_end_date, expected_end_date)

    @patch('masu.processor.tasks.update_charge_info')
    @patch(
        'masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_memory_gb_usage_per_hour_rates'
    )
    @patch(
        'masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_cpu_core_usage_per_hour_rates'
    )
    def test_update_summary_tables_ocp(
        self, mock_cpu_rate, mock_mem_rate, mock_charge_info
    ):
        """Test that the summary table task runs."""
        mem_rate = {'tiered_rate': [{'value': '1.5', 'unit': 'USD'}]}
        cpu_rate = {'tiered_rate': [{'value': '2.5', 'unit': 'USD'}]}

        mock_cpu_rate.return_value = cpu_rate
        mock_mem_rate.return_value = mem_rate

        provider = 'OCP'
        provider_ocp_uuid = self.ocp_test_provider_uuid

        daily_table_name = OCP_REPORT_TABLE_MAP['line_item_daily']
        start_date = self.start_date.replace(day=1) + relativedelta.relativedelta(
            months=-1
        )

        daily_query = self.ocp_accessor._get_db_obj_query(daily_table_name)

        initial_daily_count = daily_query.count()

        self.assertEqual(initial_daily_count, 0)
        update_summary_tables(self.schema_name, provider, provider_ocp_uuid, start_date)

        self.assertNotEqual(daily_query.count(), initial_daily_count)

        update_charge_info(
            schema_name=self.test_schema, provider_uuid=provider_ocp_uuid
        )

        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        with ProviderDBAccessor(provider_ocp_uuid) as provider_accessor:
            provider_obj = provider_accessor.get_provider()

        usage_period_qry = self.ocp_accessor.get_usage_period_query_by_provider(
            provider_obj.id
        )
        cluster_id = usage_period_qry.first().cluster_id

        items = self.ocp_accessor._get_db_obj_query(table_name).filter_by(
            cluster_id=cluster_id
        )
        for item in items:
            self.assertIsNotNone(item.pod_charge_memory_gigabyte_hours)
            self.assertIsNotNone(item.pod_charge_cpu_core_hours)

        storage_daily_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily']
        items = self.ocp_accessor._get_db_obj_query(storage_daily_name).filter_by(
            cluster_id=cluster_id
        )
        for item in items:
            self.assertIsNotNone(item.volume_request_storage_byte_seconds)
            self.assertIsNotNone(item.persistentvolumeclaim_usage_byte_seconds)

        storage_summary_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily_summary']
        items = self.ocp_accessor._get_db_obj_query(storage_summary_name).filter_by(
            cluster_id=cluster_id
        )
        for item in items:
            self.assertIsNotNone(item.volume_request_storage_gigabyte_months)
            self.assertIsNotNone(item.persistentvolumeclaim_usage_gigabyte_months)

    @patch('masu.processor.tasks.update_charge_info')
    @patch(
        'masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_memory_gb_usage_per_hour_rates'
    )
    @patch(
        'masu.database.ocp_rate_db_accessor.OCPRateDBAccessor.get_cpu_core_usage_per_hour_rates'
    )
    def test_update_summary_tables_ocp_end_date(
        self, mock_cpu_rate, mock_mem_rate, mock_charge_info
    ):
        """Test that the summary table task respects a date range."""
        mock_cpu_rate.return_value = 1.5
        mock_mem_rate.return_value = 2.5
        provider = 'OCP'
        provider_ocp_uuid = self.ocp_test_provider_uuid
        ce_table_name = OCP_REPORT_TABLE_MAP['report']
        daily_table_name = OCP_REPORT_TABLE_MAP['line_item_daily']

        start_date = self.start_date.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) + relativedelta.relativedelta(months=-1)

        end_date = start_date + timedelta(days=10)
        end_date = end_date.replace(hour=23, minute=59, second=59)

        daily_table = getattr(self.ocp_accessor.report_schema, daily_table_name)
        ce_table = getattr(self.ocp_accessor.report_schema, ce_table_name)

        ce_start_date = (
            self.ocp_accessor._session.query(func.min(ce_table.interval_start))
            .filter(ce_table.interval_start >= start_date)
            .first()[0]
        )

        ce_end_date = (
            self.ocp_accessor._session.query(func.max(ce_table.interval_start))
            .filter(ce_table.interval_start <= end_date)
            .first()[0]
        )

        # The summary tables will only include dates where there is data
        expected_start_date = max(start_date, ce_start_date)
        expected_start_date = expected_start_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        expected_end_date = min(end_date, ce_end_date)
        expected_end_date = expected_end_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        update_summary_tables(
            self.schema_name, provider, provider_ocp_uuid, start_date, end_date
        )
        result_start_date, result_end_date = self.ocp_accessor._session.query(
            func.min(daily_table.usage_start), func.max(daily_table.usage_end)
        ).first()

        self.assertEqual(result_start_date, expected_start_date)
        self.assertEqual(result_end_date, expected_end_date)

    def test_update_charge_info_aws(self):
        """Test that update_charge_info is not called for AWS."""
        update_charge_info(
            schema_name=self.test_schema, provider_uuid=self.aws_test_provider_uuid
        )
        # FIXME: no asserts on test

    @patch('masu.processor.tasks.update_summary_tables')
    def test_get_report_data_for_all_providers(self, mock_update):
        """Test GET report_data endpoint with provider_uuid=*."""
        start_date = date.today()
        update_all_summary_tables(start_date)

        mock_update.delay.assert_called_with(ANY, ANY, ANY, str(start_date), ANY)
