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
import json
import logging
import os
import shutil
import tempfile
from datetime import date
from datetime import timedelta
from decimal import Decimal
from unittest.mock import ANY
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

import faker
from dateutil import relativedelta
from django.db.models import Max
from django.db.models import Min
from tenant_schemas.utils import schema_context

import koku.celery as koku_celery
from api.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.provider_status_accessor import ProviderStatusCode
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.report_downloader import ReportDownloaderError
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.report_processor import ReportProcessorError
from masu.processor.tasks import autovacuum_tune_schema
from masu.processor.tasks import get_report_files
from masu.processor.tasks import refresh_materialized_views
from masu.processor.tasks import remove_expired_data
from masu.processor.tasks import summarize_reports
from masu.processor.tasks import update_all_summary_tables
from masu.processor.tasks import update_cost_model_costs
from masu.processor.tasks import update_summary_tables
from masu.processor.tasks import vacuum_schema
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.test.external.downloader.aws import fake_arn
from reporting.models import AWS_MATERIALIZED_VIEWS


class FakeDownloader(Mock):
    """Fake Downloader."""

    def download_report(self):
        """Get reports for fake downloader."""
        fake_file_list = [
            "/var/tmp/masu/my-report-name/aws/my-report-file.csv",
            "/var/tmp/masu/other-report-name/aws/other-report-file.csv",
        ]
        return fake_file_list


class GetReportFileTests(MasuTestCase):
    """Test Cases for the celery task."""

    fake = faker.Faker()

    @patch("masu.processor._tasks.download.ReportDownloader", return_value=FakeDownloader)
    def test_get_report(self, fake_downloader):
        """Test task."""
        account = fake_arn(service="iam", generate_account_id=True)
        report = _get_report_files(
            Mock(),
            customer_name=self.fake.word(),
            authentication=account,
            provider_type=Provider.PROVIDER_AWS,
            report_month=DateHelper().today,
            provider_uuid=self.aws_provider_uuid,
            billing_source=self.fake.word(),
            cache_key=self.fake.word(),
        )

        self.assertIsInstance(report, list)
        self.assertGreater(len(report), 0)

    @patch("masu.processor._tasks.download.ReportDownloader", return_value=FakeDownloader)
    def test_disk_status_logging(self, fake_downloader):
        """Test task for logging when temp directory exists."""
        logging.disable(logging.NOTSET)
        os.makedirs(Config.TMP_DIR, exist_ok=True)

        account = fake_arn(service="iam", generate_account_id=True)
        expected = "INFO:masu.processor._tasks.download:Available disk space"
        with self.assertLogs("masu.processor._tasks.download", level="INFO") as logger:
            _get_report_files(
                Mock(),
                customer_name=self.fake.word(),
                authentication=account,
                provider_type=Provider.PROVIDER_AWS,
                report_month=DateHelper().today,
                provider_uuid=self.aws_provider_uuid,
                billing_source=self.fake.word(),
                cache_key=self.fake.word(),
            )
            statement_found = False
            for log in logger.output:
                if expected in log:
                    statement_found = True
            self.assertTrue(statement_found)

        shutil.rmtree(Config.TMP_DIR, ignore_errors=True)

    @patch("masu.processor._tasks.download.ReportDownloader", return_value=FakeDownloader)
    def test_disk_status_logging_no_dir(self, fake_downloader):
        """Test task for logging when temp directory does not exist."""
        logging.disable(logging.NOTSET)

        Config.PVC_DIR = "/this/path/does/not/exist"

        account = fake_arn(service="iam", generate_account_id=True)
        expected = (
            "INFO:masu.processor._tasks.download:Unable to find"
            + f" available disk space. {Config.PVC_DIR} does not exist"
        )
        with self.assertLogs("masu.processor._tasks.download", level="INFO") as logger:
            _get_report_files(
                Mock(),
                customer_name=self.fake.word(),
                authentication=account,
                provider_type=Provider.PROVIDER_AWS,
                report_month=DateHelper().today,
                provider_uuid=self.aws_provider_uuid,
                billing_source=self.fake.word(),
                cache_key=self.fake.word(),
            )
            self.assertIn(expected, logger.output)

    @patch("masu.processor._tasks.download.ReportDownloader._set_downloader", side_effect=Exception("only a test"))
    def test_get_report_exception(self, fake_downloader):
        """Test task."""
        account = fake_arn(service="iam", generate_account_id=True)

        with self.assertRaises(Exception):
            _get_report_files(
                Mock(),
                customer_name=self.fake.word(),
                authentication=account,
                provider_type=Provider.PROVIDER_AWS,
                report_month=DateHelper().today,
                provider_uuid=uuid4(),
                billing_source=self.fake.word(),
                cache_key=self.fake.word(),
            )

    @patch("masu.processor._tasks.download.ProviderStatus.set_error")
    @patch(
        "masu.processor._tasks.download.ReportDownloader._set_downloader",
        side_effect=ReportDownloaderError("only a test"),
    )
    def test_get_report_exception_update_status(self, fake_downloader, fake_status):
        """Test that status is updated when an exception is raised."""
        account = fake_arn(service="iam", generate_account_id=True)

        try:
            _get_report_files(
                Mock(),
                customer_name=self.fake.word(),
                authentication=account,
                provider_type=Provider.PROVIDER_AWS,
                report_month=DateHelper().today,
                provider_uuid=self.aws_provider_uuid,
                billing_source=self.fake.word(),
                cache_key=self.fake.word(),
            )
        except ReportDownloaderError:
            pass
        fake_status.assert_called()

    @patch("masu.processor._tasks.download.ProviderStatus.set_status")
    @patch("masu.processor._tasks.download.ReportDownloader", spec=True)
    def test_get_report_update_status(self, fake_downloader, fake_status):
        """Test that status is updated when downloading is complete."""
        account = fake_arn(service="iam", generate_account_id=True)

        _get_report_files(
            Mock(),
            customer_name=self.fake.word(),
            authentication=account,
            provider_type=Provider.PROVIDER_AWS,
            report_month=DateHelper().today,
            provider_uuid=self.aws_provider_uuid,
            billing_source=self.fake.word(),
            cache_key=self.fake.word(),
        )
        fake_status.assert_called_with(ProviderStatusCode.READY)


class ProcessReportFileTests(MasuTestCase):
    """Test Cases for the Orchestrator object."""

    @patch("masu.processor._tasks.process.ProviderDBAccessor")
    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.ReportStatsDBAccessor")
    @patch("masu.processor._tasks.process.ReportManifestDBAccessor")
    def test_process_file_initial_ingest(
        self, mock_manifest_accessor, mock_stats_accessor, mock_processor, mock_provider_accessor
    ):
        """Test the process_report_file functionality on initial ingest."""
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {"file": path, "compression": "gzip", "start_date": str(DateHelper().today)}

        mock_proc = mock_processor()
        mock_stats_acc = mock_stats_accessor().__enter__()
        mock_manifest_acc = mock_manifest_accessor().__enter__()
        mock_provider_acc = mock_provider_accessor().__enter__()
        mock_provider_acc.get_setup_complete.return_value = False

        _process_report_file(schema_name, provider, provider_uuid, report_dict)

        mock_proc.process.assert_called()
        mock_proc.remove_processed_files.assert_not_called()
        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_called()
        mock_manifest_acc.mark_manifest_as_updated.assert_called()
        mock_provider_acc.setup_complete.assert_called()
        shutil.rmtree(report_dir)

    @patch("masu.processor._tasks.process.ProviderDBAccessor")
    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.ReportStatsDBAccessor")
    @patch("masu.processor._tasks.process.ReportManifestDBAccessor")
    def test_process_file_non_initial_ingest(
        self, mock_manifest_accessor, mock_stats_accessor, mock_processor, mock_provider_accessor
    ):
        """Test the process_report_file functionality on non-initial ingest."""
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {"file": path, "compression": "gzip", "start_date": str(DateHelper().today)}

        mock_proc = mock_processor()
        mock_stats_acc = mock_stats_accessor().__enter__()
        mock_manifest_acc = mock_manifest_accessor().__enter__()
        mock_provider_acc = mock_provider_accessor().__enter__()
        mock_provider_acc.get_setup_complete.return_value = True

        _process_report_file(schema_name, provider, provider_uuid, report_dict)

        mock_proc.process.assert_called()
        mock_proc.remove_processed_files.assert_called()
        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_called()
        mock_manifest_acc.mark_manifest_as_updated.assert_called()
        mock_provider_acc.setup_complete.assert_called()
        shutil.rmtree(report_dir)

    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.ReportStatsDBAccessor")
    def test_process_file_exception(self, mock_stats_accessor, mock_processor):
        """Test the process_report_file functionality when exception is thrown."""
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {"file": path, "compression": "gzip", "start_date": str(DateHelper().today)}

        mock_processor.side_effect = ReportProcessorError("mock error")
        mock_stats_acc = mock_stats_accessor().__enter__()

        with self.assertRaises(ReportProcessorError):
            _process_report_file(schema_name, provider, provider_uuid, report_dict)

        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_not_called()
        shutil.rmtree(report_dir)

    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.ReportStatsDBAccessor")
    @patch("masu.database.report_manifest_db_accessor.ReportManifestDBAccessor")
    def test_process_file_missing_manifest(self, mock_manifest_accessor, mock_stats_accessor, mock_processor):
        """Test the process_report_file functionality when manifest is missing."""
        mock_manifest_accessor.get_manifest_by_id.return_value = None
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {"file": path, "compression": "gzip", "start_date": str(DateHelper().today)}

        mock_proc = mock_processor()
        mock_stats_acc = mock_stats_accessor().__enter__()
        mock_manifest_acc = mock_manifest_accessor().__enter__()

        _process_report_file(schema_name, provider, provider_uuid, report_dict)

        mock_proc.process.assert_called()
        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_called()
        mock_manifest_acc.mark_manifest_as_updated.assert_not_called()
        shutil.rmtree(report_dir)

    @patch("masu.processor.tasks.update_summary_tables")
    def test_summarize_reports_empty_list(self, mock_update_summary):
        """Test that the summarize_reports task is called when empty processing list is provided."""
        mock_update_summary.delay = Mock()

        summarize_reports([])
        mock_update_summary.delay.assert_not_called()

    @patch("masu.processor.tasks.update_summary_tables")
    def test_summarize_reports_processing_list(self, mock_update_summary):
        """Test that the summarize_reports task is called when a processing list is provided."""
        mock_update_summary.delay = Mock()

        report_meta = {}
        report_meta["start_date"] = str(DateHelper().today)
        report_meta["schema_name"] = self.schema
        report_meta["provider_type"] = Provider.PROVIDER_OCP
        report_meta["provider_uuid"] = self.ocp_test_provider_uuid
        report_meta["manifest_id"] = 1
        reports_to_summarize = [report_meta]

        summarize_reports(reports_to_summarize)
        mock_update_summary.delay.assert_called()

    @patch("masu.processor.tasks._process_report_file")
    @patch("masu.processor.tasks._get_report_files")
    def test_process_report_files_with_transaction_atomic_error(self, mock_files, mock_processor):
        """Test than an exception rolls back the atomic transaction."""
        path = "{}/{}".format("test", "file1.csv")
        mock_files.return_value = [{"file": path, "compression": "GZIP"}]
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_month = DateHelper().today
        manifest_dict = {
            "assembly_id": "12345",
            "billing_period_start_datetime": report_month,
            "num_total_files": 1,
            "provider_uuid": self.aws_provider_uuid,
            "task": "170653c0-3e66-4b7e-a764-336496d7ca5a",
        }
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.add(**manifest_dict)
            manifest.save()
            manifest_id = manifest.id
            initial_update_time = manifest.manifest_updated_datetime

        with ReportStatsDBAccessor("file1.csv", manifest_id) as stats_accessor:
            stats_accessor.get_last_completed_datetime

        with ReportStatsDBAccessor(path, manifest_id) as report_file_accessor:
            report_file_accessor.get_last_started_datetime()

        mock_processor.side_effect = Exception

        with self.assertRaises(Exception):
            customer_name = "Fake Customer"
            authentication = "auth"
            billing_source = "bill"
            provider_type = provider
            get_report_files(
                customer_name=customer_name,
                authentication=authentication,
                billing_source=billing_source,
                provider_type=provider_type,
                schema_name=schema_name,
                provider_uuid=provider_uuid,
                report_month=report_month,
            )

        with ReportStatsDBAccessor(path, manifest_id) as report_file_accessor:
            self.assertIsNone(report_file_accessor.get_last_completed_datetime())

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(manifest_id)
            self.assertEqual(manifest.num_processed_files, 0)
            self.assertEqual(manifest.manifest_updated_datetime, initial_update_time)

        with ProviderDBAccessor(provider_uuid=provider_uuid) as provider_accessor:
            self.assertFalse(provider_accessor.get_setup_complete())


class TestProcessorTasks(MasuTestCase):
    """Test cases for Processor Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.fake = faker.Faker()
        # cls.fake_reports = [
        #     {"file": cls.fake.word(), "compression": "GZIP"},
        #     {"file": cls.fake.word(), "compression": "PLAIN"},
        # ]

        # cls.fake_account = fake_arn(service="iam", generate_account_id=True)
        cls.fake_uuid = "d4703b6e-cd1f-4253-bfd4-32bdeaf24f97"
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)

    def setUp(self):
        """Set up shared test variables."""
        super().setUp()

        self.get_report_args = {
            "customer_name": self.schema,
            "authentication": self.aws_provider.authentication.provider_resource_name,
            "provider_type": Provider.PROVIDER_AWS_LOCAL,
            "schema_name": self.schema,
            "billing_source": self.aws_provider.billing_source.bucket,
            "provider_uuid": self.aws_provider_uuid,
            "report_month": DateHelper().today.date(),
        }

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime")
    @patch("masu.processor.tasks._get_report_files")
    @patch("masu.processor.tasks._process_report_file", side_effect=ReportProcessorError("Mocked Error!"))
    def test_get_report_exception(self, mock_process_files, mock_get_files, mock_started, mock_completed):
        """Test raising processor exception is handled."""
        mock_get_files.return_value = [
            {"file": self.fake.word(), "compression": "GZIP"},
            {"file": self.fake.word(), "compression": "PLAIN"},
        ]
        mock_started.return_value = None

        # Check that exception is raised
        with self.assertRaises(ReportProcessorError):
            # Check that the exception logs an ERROR
            with self.assertLogs("masu.processor.tasks.get_report_files", level="ERROR"):
                get_report_files(**self.get_report_args)

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime")
    def test_get_report_files_timestamps_aligned(self, mock_started, mock_completed):
        """Test to return reports only when they have not been processed."""
        mock_started.return_value = self.yesterday
        mock_completed.return_value = self.today

        reports = get_report_files(**self.get_report_args)
        self.assertEqual(reports, [])

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime")
    def test_get_report_files_timestamps_misaligned(self, mock_started, mock_completed):
        """Test to return reports with misaligned timestamps."""
        mock_started.return_value = self.today
        mock_completed.return_value = self.yesterday

        reports = get_report_files(**self.get_report_args)
        self.assertEqual(reports, [])

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime")
    @patch("masu.processor.tasks._process_report_file")
    def test_get_report_files_timestamps_empty_start(self, mock_process_files, mock_started, mock_completed):
        """Test that the chained task is called when no start time is set."""
        mock_process_files.apply_async = Mock()

        mock_started.return_value = None
        mock_completed.return_value = self.today
        reports = get_report_files(**self.get_report_args)
        self.assertIsNotNone(reports)

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime")
    @patch("masu.external.date_accessor.DateAccessor.today")
    def test_get_report_files_timestamps_empty_end(self, mock_date, mock_started, mock_completed):
        """Chained task is not called when no end time is set since processing is in progress."""
        mock_started.return_value = self.today

        # Make sure today() is only an hour from get_last_started_datetime (within 2 hr timeout)
        mock_date.return_value = self.today + timedelta(hours=1)

        mock_completed.return_value = None
        reports = get_report_files(**self.get_report_args)
        self.assertEqual(reports, [])

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime")
    @patch("masu.processor.tasks._process_report_file")
    @patch("masu.external.date_accessor.DateAccessor.today_with_timezone")
    def test_get_report_files_timestamps_empty_end_timeout(
        self, mock_date, mock_process_files, mock_started, mock_completed
    ):
        """Chained task is called when no end time is set since processing has exceeded the timeout."""
        mock_process_files.apply_async = Mock()

        mock_started.return_value = self.today
        mock_completed.return_value = None

        mock_date.return_value = self.today + timedelta(hours=3)
        reports = get_report_files(**self.get_report_args)
        self.assertIsNotNone(reports)

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime")
    @patch("masu.processor.tasks._process_report_file")
    @patch("masu.external.date_accessor.DateAccessor.today_with_timezone")
    def test_get_report_files_timestamps_empty_end_no_timeout(
        self, mock_date, mock_process_files, mock_started, mock_completed
    ):
        """
        Chained task is not called when no end time is set.

        Since processing is in progress but completion timeout has not been reached.
        """
        mock_started.return_value = self.today
        mock_completed.return_value = None

        mock_date.return_value = self.today + timedelta(hours=1)

        reports = get_report_files(**self.get_report_args)
        self.assertIsNotNone(reports)

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_started_datetime")
    @patch("masu.processor.tasks._process_report_file")
    def test_get_report_files_timestamps_empty_both(self, mock_process_file, mock_started, mock_completed):
        """Test that the chained task is called when no timestamps are set."""
        mock_process_file.return_value = None

        mock_started.return_value = None
        mock_completed.return_value = None
        reports = get_report_files(**self.get_report_args)
        self.assertIsNotNone(reports)


class TestRemoveExpiredDataTasks(MasuTestCase):
    """Test cases for Processor Celery tasks."""

    @patch.object(ExpiredDataRemover, "remove")
    @patch("masu.processor.tasks.refresh_materialized_views.delay")
    def test_remove_expired_data(self, fake_view, fake_remover):
        """Test task."""
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        fake_remover.return_value = expected_results

        expected = "INFO:masu.processor._tasks.remove_expired:Expired Data:\n {}"

        # disable logging override set in masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs("masu.processor._tasks.remove_expired") as logger:
            remove_expired_data(schema_name=self.schema, provider=Provider.PROVIDER_AWS, simulate=True)
            self.assertIn(expected.format(str(expected_results)), logger.output)

    @patch.object(ExpiredDataRemover, "remove")
    @patch("masu.processor.tasks.refresh_materialized_views.delay")
    def test_remove_expired_line_items_only(self, fake_view, fake_remover):
        """Test task."""
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        fake_remover.return_value = expected_results

        expected = "INFO:masu.processor._tasks.remove_expired:Expired Data:\n {}"

        # disable logging override set in masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs("masu.processor._tasks.remove_expired") as logger:
            remove_expired_data(
                schema_name=self.schema, provider=Provider.PROVIDER_AWS, simulate=True, line_items_only=True
            )
            self.assertIn(expected.format(str(expected_results)), logger.output)


class TestUpdateSummaryTablesTask(MasuTestCase):
    """Test cases for Processor summary table Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up for the class."""
        super().setUpClass()
        cls.aws_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.ocp_tables = list(OCP_REPORT_TABLE_MAP.values())
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values()) + list(OCP_REPORT_TABLE_MAP.values())

        cls.creator = ReportObjectCreator(cls.schema)

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.aws_accessor = AWSReportDBAccessor(schema=self.schema)
        self.ocp_accessor = OCPReportDBAccessor(schema=self.schema)

        # Populate some line item data so that the summary tables
        # have something to pull from
        self.start_date = DateHelper().today.replace(day=1)

    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.refresh_materialized_views")
    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_update_summary_tables_aws(self, mock_charge_info, mock_views, mock_chain):
        """Test that the summary table task runs."""
        provider = Provider.PROVIDER_AWS
        provider_aws_uuid = self.aws_provider_uuid

        daily_table_name = AWS_CUR_TABLE_MAP["line_item_daily"]
        summary_table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]
        start_date = self.start_date.replace(day=1) + relativedelta.relativedelta(months=-1)

        with schema_context(self.schema):
            daily_query = self.aws_accessor._get_db_obj_query(daily_table_name)
            summary_query = self.aws_accessor._get_db_obj_query(summary_table_name)
            daily_query.delete()
            summary_query.delete()

            initial_daily_count = daily_query.count()
            initial_summary_count = summary_query.count()

        self.assertEqual(initial_daily_count, 0)
        self.assertEqual(initial_summary_count, 0)

        update_summary_tables(self.schema, provider, provider_aws_uuid, start_date)

        with schema_context(self.schema):
            self.assertNotEqual(daily_query.count(), initial_daily_count)
            self.assertNotEqual(summary_query.count(), initial_summary_count)

        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.processor.tasks.update_cost_model_costs")
    def test_update_summary_tables_aws_end_date(self, mock_charge_info):
        """Test that the summary table task respects a date range."""
        provider = Provider.PROVIDER_AWS_LOCAL
        provider_aws_uuid = self.aws_provider_uuid
        ce_table_name = AWS_CUR_TABLE_MAP["cost_entry"]
        daily_table_name = AWS_CUR_TABLE_MAP["line_item_daily"]
        summary_table_name = AWS_CUR_TABLE_MAP["line_item_daily_summary"]

        start_date = DateHelper().last_month_start

        end_date = DateHelper().last_month_end

        daily_table = getattr(self.aws_accessor.report_schema, daily_table_name)
        summary_table = getattr(self.aws_accessor.report_schema, summary_table_name)
        ce_table = getattr(self.aws_accessor.report_schema, ce_table_name)
        with schema_context(self.schema):
            daily_table.objects.all().delete()
            summary_table.objects.all().delete()
            ce_start_date = ce_table.objects.filter(interval_start__gte=start_date.date()).aggregate(
                Min("interval_start")
            )["interval_start__min"]
            ce_end_date = ce_table.objects.filter(interval_start__lte=end_date.date()).aggregate(
                Max("interval_start")
            )["interval_start__max"]

        # The summary tables will only include dates where there is data
        expected_start_date = max(start_date, ce_start_date)
        expected_start_date = expected_start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        expected_end_date = min(end_date, ce_end_date)
        expected_end_date = expected_end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        update_summary_tables(self.schema, provider, provider_aws_uuid, start_date, end_date)

        with schema_context(self.schema):
            daily_entry = daily_table.objects.all().aggregate(Min("usage_start"), Max("usage_end"))
            result_start_date = daily_entry["usage_start__min"]
            result_end_date = daily_entry["usage_end__max"]

        self.assertEqual(result_start_date, expected_start_date.date())
        self.assertEqual(result_end_date, expected_end_date.date())

        with schema_context(self.schema):
            summary_entry = summary_table.objects.all().aggregate(Min("usage_start"), Max("usage_end"))
            result_start_date = summary_entry["usage_start__min"]
            result_end_date = summary_entry["usage_end__max"]

        self.assertEqual(result_start_date, expected_start_date.date())
        self.assertEqual(result_end_date, expected_end_date.date())

    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.refresh_materialized_views")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_summary_tables_ocp(self, mock_cost_model, mock_charge_info, mock_view, mock_chain):
        """Test that the summary table task runs."""
        infrastructure_rates = {
            "cpu_core_usage_per_hour": 1.5,
            "memory_gb_usage_per_hour": 2.5,
            "storage_gb_usage_per_month": 0.5,
        }
        markup = {}

        mock_cost_model.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_model.return_value.__enter__.return_value.supplementary_rates = {}
        mock_cost_model.return_value.__enter__.return_value.markup = markup

        provider = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid

        daily_table_name = OCP_REPORT_TABLE_MAP["line_item_daily"]
        start_date = DateHelper().last_month_start
        end_date = DateHelper().last_month_end

        with schema_context(self.schema):
            daily_query = self.ocp_accessor._get_db_obj_query(daily_table_name)
            daily_query.delete()

            initial_daily_count = daily_query.count()

        self.assertEqual(initial_daily_count, 0)
        update_summary_tables(self.schema, provider, provider_ocp_uuid, start_date, end_date)

        with schema_context(self.schema):
            self.assertNotEqual(daily_query.count(), initial_daily_count)

        update_cost_model_costs(
            schema_name=self.schema, provider_uuid=provider_ocp_uuid, start_date=start_date, end_date=end_date
        )

        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        with ProviderDBAccessor(provider_ocp_uuid) as provider_accessor:
            provider_obj = provider_accessor.get_provider()

        usage_period_qry = self.ocp_accessor.get_usage_period_query_by_provider(provider_obj.uuid)
        with schema_context(self.schema):
            cluster_id = usage_period_qry.first().cluster_id

            items = self.ocp_accessor._get_db_obj_query(table_name).filter(
                usage_start__gte=start_date, usage_start__lte=end_date, cluster_id=cluster_id, data_source="Pod"
            )
            for item in items:
                self.assertNotEqual(item.infrastructure_usage_cost.get("cpu"), 0)
                self.assertNotEqual(item.infrastructure_usage_cost.get("memory"), 0)

            storage_daily_name = OCP_REPORT_TABLE_MAP["storage_line_item_daily"]

            items = self.ocp_accessor._get_db_obj_query(storage_daily_name).filter(cluster_id=cluster_id)
            for item in items:
                self.assertIsNotNone(item.volume_request_storage_byte_seconds)
                self.assertIsNotNone(item.persistentvolumeclaim_usage_byte_seconds)

            storage_summary_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
            items = self.ocp_accessor._get_db_obj_query(storage_summary_name).filter(
                cluster_id=cluster_id, data_source="Storage"
            )
            for item in items:
                self.assertIsNotNone(item.volume_request_storage_gigabyte_months)
                self.assertIsNotNone(item.persistentvolumeclaim_usage_gigabyte_months)

        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.database.cost_model_db_accessor.CostModelDBAccessor.get_memory_gb_usage_per_hour_rates")
    @patch("masu.database.cost_model_db_accessor.CostModelDBAccessor.get_cpu_core_usage_per_hour_rates")
    def test_update_summary_tables_ocp_end_date(self, mock_cpu_rate, mock_mem_rate, mock_charge_info):
        """Test that the summary table task respects a date range."""
        mock_cpu_rate.return_value = 1.5
        mock_mem_rate.return_value = 2.5
        provider = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid
        ce_table_name = OCP_REPORT_TABLE_MAP["report"]
        daily_table_name = OCP_REPORT_TABLE_MAP["line_item_daily"]

        start_date = DateHelper().last_month_start
        end_date = DateHelper().last_month_end
        daily_table = getattr(self.ocp_accessor.report_schema, daily_table_name)
        ce_table = getattr(self.ocp_accessor.report_schema, ce_table_name)

        with schema_context(self.schema):
            daily_table.objects.all().delete()
            ce_start_date = ce_table.objects.filter(interval_start__gte=start_date.date()).aggregate(
                Min("interval_start")
            )["interval_start__min"]

            ce_end_date = ce_table.objects.filter(interval_start__lte=end_date.date()).aggregate(
                Max("interval_start")
            )["interval_start__max"]

        # The summary tables will only include dates where there is data
        expected_start_date = max(start_date, ce_start_date)
        expected_end_date = min(end_date, ce_end_date)

        update_summary_tables(self.schema, provider, provider_ocp_uuid, start_date, end_date)
        with schema_context(self.schema):
            daily_entry = daily_table.objects.all().aggregate(Min("usage_start"), Max("usage_end"))
            result_start_date = daily_entry["usage_start__min"]
            result_end_date = daily_entry["usage_end__max"]

        self.assertEqual(result_start_date, expected_start_date.date())
        self.assertEqual(result_end_date, expected_end_date.date())

    @patch("masu.processor.tasks.update_summary_tables")
    def test_get_report_data_for_all_providers(self, mock_update):
        """Test GET report_data endpoint with provider_uuid=*."""
        start_date = date.today()
        update_all_summary_tables(start_date)

        mock_update.delay.assert_called_with(ANY, ANY, ANY, str(start_date), ANY)

    def test_refresh_materialized_views(self):
        """Test that materialized views are refreshed."""
        manifest_dict = {
            "assembly_id": "12345",
            "billing_period_start_datetime": DateHelper().today,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
            "task": "170653c0-3e66-4b7e-a764-336496d7ca5a",
        }

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.add(**manifest_dict)
            manifest.save()

        refresh_materialized_views(self.schema, Provider.PROVIDER_AWS, manifest_id=manifest.id)

        views_to_check = [view for view in AWS_MATERIALIZED_VIEWS if "Cost" in view._meta.db_table]

        with schema_context(self.schema):
            for view in views_to_check:
                self.assertNotEqual(view.objects.count(), 0)

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(manifest.id)
            self.assertIsNotNone(manifest.manifest_completed_datetime)

    @patch("masu.processor.tasks.connection")
    def test_vacuum_schema(self, mock_conn):
        """Test that the vacuum schema task runs."""
        logging.disable(logging.NOTSET)
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("table",)]
        expected = "INFO:masu.processor.tasks:VACUUM ANALYZE acct10001.table"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            vacuum_schema(self.schema)
            self.assertIn(expected, logger.output)

    @patch("masu.processor.tasks.connection")
    def test_autovacuum_tune_schema_default_table(self, mock_conn):
        """Test that the autovacuum tuning runs."""
        logging.disable(logging.NOTSET)

        # Make sure that the AUTOVACUUM_TUNING environment variable is unset!
        if "AUTOVACUUM_TUNING" in os.environ:
            del os.environ["AUTOVACUUM_TUNING"]

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 20000000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model set (autovacuum_vacuum_scale_factor = 0.01);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 2000000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model set (autovacuum_vacuum_scale_factor = 0.02);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 200000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model set (autovacuum_vacuum_scale_factor = 0.05);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("cost_model", 200000, {"autovacuum_vacuum_scale_factor": Decimal("0.05")})
        ]
        expected = "INFO:masu.processor.tasks:Altered autovacuum_vacuum_scale_factor on 0 tables"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("cost_model", 20000, {"autovacuum_vacuum_scale_factor": Decimal("0.02")})
        ]
        expected = "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model reset (autovacuum_vacuum_scale_factor);"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

    @patch("masu.processor.tasks.connection")
    def test_autovacuum_tune_schema_custom_table(self, mock_conn):
        """Test that the autovacuum tuning runs."""
        logging.disable(logging.NOTSET)
        scale_table = [(10000000, "0.0001"), (1000000, "0.004"), (100000, "0.011")]
        os.environ["AUTOVACUUM_TUNING"] = json.dumps(scale_table)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 20000000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model set (autovacuum_vacuum_scale_factor = 0.0001);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 2000000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model set (autovacuum_vacuum_scale_factor = 0.004);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 200000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model set (autovacuum_vacuum_scale_factor = 0.011);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("cost_model", 200000, {"autovacuum_vacuum_scale_factor": Decimal("0.011")})
        ]
        expected = "INFO:masu.processor.tasks:Altered autovacuum_vacuum_scale_factor on 0 tables"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("cost_model", 20000, {"autovacuum_vacuum_scale_factor": Decimal("0.004")})
        ]
        expected = "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model reset (autovacuum_vacuum_scale_factor);"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        del os.environ["AUTOVACUUM_TUNING"]

    @patch("masu.processor.tasks.connection")
    def test_autovacuum_tune_schema_manual_setting(self, mock_conn):
        """Test that the autovacuum tuning runs."""
        logging.disable(logging.NOTSET)

        # Make sure that the AUTOVACUUM_TUNING environment variable is unset!
        if "AUTOVACUUM_TUNING" in os.environ:
            del os.environ["AUTOVACUUM_TUNING"]

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("cost_model", 200000, {"autovacuum_vacuum_scale_factor": Decimal("0.04")})
        ]
        expected = "INFO:masu.processor.tasks:Altered autovacuum_vacuum_scale_factor on 0 tables"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("cost_model", 200000, {"autovacuum_vacuum_scale_factor": Decimal("0.06")})
        ]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE acct10001.cost_model set (autovacuum_vacuum_scale_factor = 0.05);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

    def test_autovacuum_tune_schedule(self):
        vh = next(iter(koku_celery.app.conf.beat_schedule["vacuum-schemas"]["schedule"].hour))
        avh = next(iter(koku_celery.app.conf.beat_schedule["autovacuum-tune-schemas"]["schedule"].hour))
        self.assertTrue(avh == (23 if vh == 0 else (vh - 1)))
