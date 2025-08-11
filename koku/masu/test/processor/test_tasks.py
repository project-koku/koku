#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the download task."""
import datetime
import json
import logging
import os
import shutil
import tempfile
import time
from datetime import date
from datetime import timedelta
from decimal import Decimal
from unittest import skip
from unittest.mock import ANY
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

import faker
from cachetools import TTLCache
from dateutil import relativedelta
from django.conf import settings
from django.core.cache import caches
from django.db.utils import IntegrityError
from django.test.utils import override_settings
from django_tenants.utils import schema_context

from api.iam.models import Tenant
from api.models import Provider
from common.queues import SummaryQueue
from koku.cache import CacheEnum
from koku.middleware import KokuTenantMiddleware
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.exceptions import MasuProcessingError
from masu.exceptions import MasuProviderError
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
from masu.external.report_downloader import ReportDownloaderError
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.processor.report_processor import ReportProcessorError
from masu.processor.report_summary_updater import ReportSummaryUpdaterCloudError
from masu.processor.report_summary_updater import ReportSummaryUpdaterError
from masu.processor.report_summary_updater import ReportSummaryUpdaterProviderNotFoundError
from masu.processor.tasks import autovacuum_tune_schema
from masu.processor.tasks import get_report_files
from masu.processor.tasks import mark_manifest_complete
from masu.processor.tasks import normalize_table_options
from masu.processor.tasks import record_all_manifest_files
from masu.processor.tasks import record_report_status
from masu.processor.tasks import remove_expired_data
from masu.processor.tasks import remove_expired_trino_partitions
from masu.processor.tasks import remove_stale_tenants
from masu.processor.tasks import summarize_reports
from masu.processor.tasks import update_all_summary_tables
from masu.processor.tasks import update_cost_model_costs
from masu.processor.tasks import update_openshift_on_cloud
from masu.processor.tasks import update_summary_tables
from masu.processor.tasks import validate_daily_data
from masu.processor.worker_cache import create_single_task_cache_key
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn
from reporting.ingress.models import IngressReports
from reporting.models import OCPUsageLineItemDailySummary
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


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
            report_month=self.dh.today,
            provider_uuid=self.aws_provider_uuid,
            billing_source=self.fake.word(),
            report_context={"manifest_id": 1},
        )

        self.assertIsInstance(report, list)
        self.assertGreater(len(report), 0)

    @patch("masu.processor._tasks.download.ReportDownloader", return_value=FakeDownloader)
    def test_disk_status_logging(self, fake_downloader):
        """Test task for logging when temp directory exists."""
        logging.disable(logging.NOTSET)
        os.makedirs(Config.TMP_DIR, exist_ok=True)

        account = fake_arn(service="iam", generate_account_id=True)
        expected = "Available disk space"
        with self.assertLogs("masu.processor._tasks.download", level="INFO") as logger:
            _get_report_files(
                Mock(),
                customer_name=self.fake.word(),
                authentication=account,
                provider_type=Provider.PROVIDER_AWS,
                report_month=self.dh.today,
                provider_uuid=self.aws_provider_uuid,
                billing_source=self.fake.word(),
                report_context={"manifest_id": 1},
            )
            statement_found = any(expected in log for log in logger.output)
            self.assertTrue(statement_found)

        shutil.rmtree(Config.TMP_DIR, ignore_errors=True)

    @patch("masu.processor._tasks.download.ReportDownloader", return_value=FakeDownloader)
    def test_disk_status_logging_no_dir(self, fake_downloader):
        """Test task for logging when temp directory does not exist."""
        logging.disable(logging.NOTSET)

        Config.DATA_DIR = "/this/path/does/not/exist"

        account = fake_arn(service="iam", generate_account_id=True)
        expected = "Unable to find" + f" available disk space. {Config.DATA_DIR} does not exist"
        with self.assertLogs("masu.processor._tasks.download", level="INFO") as logger:
            _get_report_files(
                Mock(),
                customer_name=self.fake.word(),
                authentication=account,
                provider_type=Provider.PROVIDER_AWS,
                report_month=self.dh.today,
                provider_uuid=self.aws_provider_uuid,
                billing_source=self.fake.word(),
                report_context={"manifest_id": 1},
            )
            statement_found = any(expected in log for log in logger.output)
            self.assertTrue(statement_found)

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor._tasks.download.ReportDownloader._set_downloader", side_effect=Exception("only a test"))
    def test_get_report_task_exception(self, fake_downloader, mock_inspect):
        """Test task."""
        account = fake_arn(service="iam", generate_account_id=True)

        with self.assertRaises(Exception):
            _get_report_files(
                Mock(),
                customer_name=self.fake.word(),
                authentication=account,
                provider_type=Provider.PROVIDER_AWS,
                report_month=self.dh.today,
                provider_uuid=uuid4(),
                billing_source=self.fake.word(),
                report_context={},
            )


class ProcessReportFileTests(MasuTestCase):
    """Test Cases for the Orchestrator object."""

    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    def test_process_file_initial_ingest(self, mock_stats, mock_processor):
        """Test the process_report_file functionality on initial ingest."""
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(self.dh.today),
            "provider_uuid": provider_uuid,
        }

        mock_proc = mock_processor()
        mock_stats.get.return_value = mock_stats
        self.aws_provider.refresh_from_db()
        self.assertFalse(self.aws_provider.setup_complete)

        _process_report_file(schema_name, provider, report_dict)

        mock_proc.process.assert_called()
        mock_stats.set_started_datetime.assert_called()
        mock_stats.set_completed_datetime.assert_called()
        self.aws_provider.refresh_from_db()
        self.assertTrue(self.aws_provider.setup_complete)
        shutil.rmtree(report_dir)

    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    def test_process_file_non_initial_ingest(self, mock_stats, mock_processor):
        """Test the process_report_file functionality on non-initial ingest."""
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(self.dh.today),
            "provider_uuid": provider_uuid,
        }

        mock_proc = mock_processor()
        mock_stats.get.return_value = mock_stats
        self.aws_provider.set_setup_complete()

        _process_report_file(schema_name, provider, report_dict)

        mock_proc.process.assert_called()
        mock_stats.set_started_datetime.assert_called()
        mock_stats.set_completed_datetime.assert_called()
        shutil.rmtree(report_dir)

    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    def test_process_file_exception(self, mock_stats, mock_processor):
        """Test the process_report_file functionality when exception is thrown."""
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(self.dh.today),
            "provider_uuid": provider_uuid,
            "manifest_id": 1,
        }

        mock_processor.side_effect = ReportProcessorError("mock error")
        mock_stats.get.return_value = mock_stats

        with self.assertRaises(ReportProcessorError):
            _process_report_file(schema_name, provider, report_dict)

        mock_stats.set_started_datetime.assert_called()
        mock_stats.set_completed_datetime.assert_not_called()
        shutil.rmtree(report_dir)

    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    def test_process_file_not_implemented_exception(self, mock_stats, mock_processor):
        """Test the process_report_file functionality when exception is thrown."""
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(self.dh.today),
            "provider_uuid": provider_uuid,
            "manifest_id": 1,
        }

        mock_processor.side_effect = NotImplementedError("mock error")
        mock_stats.get.return_value = mock_stats

        with self.assertRaises(NotImplementedError):
            _process_report_file(schema_name, provider, report_dict)

        mock_stats.set_started_datetime.assert_called()
        mock_stats.set_completed_datetime.assert_called()
        shutil.rmtree(report_dir)

    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    @patch("masu.database.report_manifest_db_accessor.ReportManifestDBAccessor")
    def test_process_file_missing_manifest(self, mock_manifest_accessor, mock_stats, mock_processor):
        """Test the process_report_file functionality when manifest is missing."""
        mock_manifest_accessor.get_manifest_by_id.return_value = None
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(self.dh.today),
            "provider_uuid": provider_uuid,
            "manifest_id": 1,
        }

        mock_proc = mock_processor()
        mock_stats.get.return_value = mock_stats

        _process_report_file(schema_name, provider, report_dict)

        mock_proc.process.assert_called()
        mock_stats.set_started_datetime.assert_called()
        mock_stats.set_completed_datetime.assert_called()
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
        providers = [
            {"type": Provider.PROVIDER_OCP, "uuid": self.ocp_test_provider_uuid},
            {"type": Provider.PROVIDER_GCP, "uuid": self.gcp_test_provider_uuid},
        ]
        test_date = datetime.datetime(2023, 3, 3, tzinfo=settings.UTC)

        for provider_dict in providers:
            invoice_month = self.dh.gcp_find_invoice_months_in_date_range(self.dh.yesterday, self.dh.today)[0]
            provider_type = provider_dict.get("type")
            provider_uuid = provider_dict.get("uuid")

            with self.subTest(provider_dict=provider_dict):
                mock_update_summary.s = Mock()
                report_meta = {}
                report_meta["start_date"] = test_date.strftime("%Y-%m-%d")
                report_meta["schema_name"] = self.schema
                report_meta["provider_type"] = provider_type
                report_meta["provider_uuid"] = provider_uuid
                report_meta["manifest_id"] = 1
                report_meta["start"] = test_date.strftime("%Y-%m-%d")
                report_meta["end"] = test_date.strftime("%Y-%m-%d")
                if provider_type == Provider.PROVIDER_GCP:
                    report_meta["invoice_month"] = invoice_month

                # add a report with start/end dates specified
                report2_meta = {}
                report2_meta["start_date"] = test_date.strftime("%Y-%m-%d")
                report2_meta["schema_name"] = self.schema
                report2_meta["provider_type"] = provider_type
                report2_meta["provider_uuid"] = provider_uuid
                report2_meta["manifest_id"] = 2
                report2_meta["start"] = test_date.strftime("%Y-%m-%d")
                report2_meta["end"] = test_date.strftime("%Y-%m-%d")
                if provider_type == Provider.PROVIDER_GCP:
                    report2_meta["invoice_month"] = invoice_month

                reports_to_summarize = [report_meta, report2_meta]

                summarize_reports(reports_to_summarize)
                mock_update_summary.s.assert_called()

    @patch("masu.processor.tasks.update_summary_tables")
    def test_summarize_reports_processing_with_XL_queue(self, mock_update_summary):
        """Test that the summarize_reports task is called with XL queue."""
        test_date = datetime.datetime(2023, 3, 3, tzinfo=settings.UTC)
        provider_type = Provider.PROVIDER_OCP
        provider_uuid = self.ocp_test_provider_uuid
        report_meta = {}
        report_meta["start_date"] = test_date.strftime("%Y-%m-%d")
        report_meta["schema_name"] = self.schema
        report_meta["provider_type"] = provider_type
        report_meta["provider_uuid"] = provider_uuid
        report_meta["manifest_id"] = 1
        reports_to_summarize = [report_meta]
        with patch("masu.processor.tasks.get_customer_queue", return_value=SummaryQueue.XL):
            summarize_reports(reports_to_summarize)
            mock_update_summary.s.return_value.apply_async.assert_called_with(queue=SummaryQueue.XL)

    @patch("masu.processor.tasks.update_summary_tables")
    def test_summarize_reports_processing_list_with_none(self, mock_update_summary):
        """Test that the summarize_reports task is called when a processing list with a None provided."""
        mock_update_summary.s = Mock()

        report_meta = {
            "start": str(self.dh.today),
            "end": str(self.dh.today),
            "schema_name": self.schema,
            "provider_type": Provider.PROVIDER_OCP,
            "provider_uuid": self.ocp_test_provider_uuid,
            "manifest_id": 1,
        }
        reports_to_summarize = [report_meta, None]

        summarize_reports(reports_to_summarize)

        mock_update_summary.s.assert_called()

    @patch("masu.processor.tasks.update_summary_tables")
    def test_summarize_reports_processing_list_only_none(self, mock_update_summary):
        """Test that the summarize_reports task is called when a processing list with only None provided."""
        mock_update_summary.s = Mock()
        reports_to_summarize = [None, None]

        summarize_reports(reports_to_summarize)
        mock_update_summary.s.assert_not_called()


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
        cls.today = cls.dh.today
        cls.yesterday = cls.today - timedelta(days=1)

    def setUp(self):
        """Set up shared test variables."""
        super().setUp()
        self.test_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        self.test_etag = "fake_etag"
        self.get_report_args = {
            "customer_name": self.schema,
            "authentication": self.aws_provider.authentication.credentials,
            "provider_type": Provider.PROVIDER_AWS_LOCAL,
            "schema_name": self.schema,
            "billing_source": self.aws_provider.billing_source.data_source,
            "provider_uuid": self.aws_provider_uuid,
            "report_month": self.today,
            "report_context": {"current_file": f"/my/{self.test_assembly_id}/koku-1.csv.gz"},
            "tracing_id": "my-totally-made-up-id",
        }
        self.get_report_args_gcp = {
            "customer_name": self.schema,
            "authentication": self.gcp_provider.authentication.credentials,
            "provider_type": Provider.PROVIDER_GCP_LOCAL,
            "schema_name": self.schema,
            "billing_source": self.gcp_provider.billing_source.data_source,
            "provider_uuid": self.gcp_provider_uuid,
            "report_month": self.today,
            "report_context": {"current_file": f"/my/{self.test_assembly_id}/koku-1.csv.gz"},
            "tracing_id": "my-totally-made-up-id",
        }

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._process_report_file")
    def test_get_report_files_exception(self, mock_process_files, mock_inspect, mock_cache_remove):
        """Test raising download exception is handled."""
        exceptions = [MasuProcessingError, MasuProviderError, ReportDownloaderError]
        for exception in exceptions:
            with self.subTest(exception=exception):
                with patch(
                    "masu.processor.tasks._get_report_files", side_effect=exception("Mocked exception!")
                ) as mock_get_files:
                    get_report_files(**self.get_report_args)
                    mock_get_files.assert_called()
                    mock_cache_remove.assert_called()
                    mock_process_files.assert_not_called()

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._process_report_file")
    def test_get_report_files_report_dict_none(self, mock_process_files, mock_inspect, mock_cache_remove):
        """Test raising download exception is handled."""
        expected_log = "no report to be processed"
        with patch("masu.processor.tasks._get_report_files", return_value=None) as mock_get_files:
            with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
                get_report_files(**self.get_report_args)
                mock_get_files.assert_called()
                mock_cache_remove.assert_called()
                mock_process_files.assert_not_called()
                self.assertIn(expected_log.lower(), logger.output[0].lower())

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._get_report_files")
    @patch("masu.processor.tasks._process_report_file")
    def test_get_report_files_report_dict_invoice_month(
        self, mock_process_files, mock_get_files, mock_inspect, mock_cache_remove
    ):
        """Test raising download exception is handled."""
        expected_log = "'invoice_month': '202201'"
        mock_get_files.return_value = {"file": self.fake.word(), "compression": "GZIP", "invoice_month": "202201"}
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            get_report_files(**self.get_report_args_gcp)
            self.assertIn(expected_log, logger.output[0])

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._get_report_files")
    @patch("masu.processor.tasks._process_report_file", side_effect=ReportProcessorError("Mocked process error!"))
    def test_get_report_process_exception(self, mock_process_files, mock_get_files, mock_inspect, mock_cache_remove):
        """Test raising processor exception is handled."""
        mock_get_files.return_value = {"file": self.fake.word(), "compression": "GZIP"}

        get_report_files(**self.get_report_args)
        mock_cache_remove.assert_called()

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._get_report_files")
    @patch("masu.processor.tasks._process_report_file", side_effect=NotImplementedError)
    def test_get_report_process_not_implemented_error(
        self, mock_process_files, mock_get_files, mock_inspect, mock_cache_remove
    ):
        """Test raising processor exception is handled."""
        mock_get_files.return_value = {"file": self.fake.word(), "compression": "PLAIN"}

        get_report_files(**self.get_report_args)
        mock_cache_remove.assert_called()

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._get_report_files")
    @patch("masu.processor.tasks._process_report_file", return_value=False)
    def test_get_report_files_returns_none(self, mock_process_files, mock_get_files, mock_inspect, mock_cache_remove):
        """Test to check no reports are return for summary after failed csv to parquet conversion."""
        mock_get_files.return_value = {"file": self.fake.word(), "compression": "PLAIN"}

        result = get_report_files(**self.get_report_args)
        mock_cache_remove.assert_called()
        self.assertFalse(result)

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._get_report_files", side_effect=Exception("Mocked download error!"))
    def test_get_report_broad_exception(self, mock_get_files, mock_inspect, mock_cache_remove):
        """Test raising download broad exception is handled."""
        mock_get_files.return_value = {"file": self.fake.word(), "compression": "GZIP"}

        get_report_files(**self.get_report_args)
        mock_cache_remove.assert_called()

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._get_report_files", side_effect=ReportDownloaderWarning("Mocked download warning!"))
    def test_get_report_download_warning(self, mock_get_files, mock_inspect, mock_cache_remove):
        """Test raising download warning is handled."""
        mock_get_files.return_value = {"file": self.fake.word(), "compression": "GZIP"}

        get_report_files(**self.get_report_args)
        mock_cache_remove.assert_called()

    @patch("masu.processor.tasks.DataValidator")
    @patch(
        "masu.processor.tasks.is_validation_enabled",
        return_value=True,
    )
    def test_validate_data_task(self, mock_unleash, mock_validate_daily_data):
        """Test validate data task."""
        context = {"unit": "test"}
        validate_daily_data(self.schema, self.start_date, self.start_date, self.aws_provider_uuid, context=context)
        mock_validate_daily_data.assert_called()

    @patch("masu.processor.tasks.DataValidator")
    def test_validate_data_task_skip(self, mock_validate_daily_data):
        """Test skipping validate data task."""
        context = {"unit": "test"}
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            validate_daily_data(self.schema, self.start_date, self.start_date, self.aws_provider_uuid, context=context)
            mock_validate_daily_data.assert_not_called()
            expected = "skipping validation, disabled for schema"
            found = any(expected in log for log in logger.output)
            self.assertTrue(found)


class TestRemoveExpiredDataTasks(MasuTestCase):
    """Test cases for Processor Celery tasks."""

    @patch.object(ExpiredDataRemover, "remove")
    def test_remove_expired_data_simulate(self, fake_remover):
        """Test task."""
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        fake_remover.return_value = expected_results

        schema = self.schema
        provider = Provider.PROVIDER_AWS
        simulate = True

        expected_initial_remove_log = (
            "INFO:masu.processor._tasks.remove_expired:"
            "{'message': 'Remove expired data', 'tracing_id': '', "
            "'schema': '" + schema + "', "
            "'provider_type': '" + provider + "', "
            "'provider_uuid': " + str(None) + ", "
            "'simulate': " + str(simulate) + "}"
        )

        expected_expired_data_log = (
            "INFO:masu.processor._tasks.remove_expired:"
            "{'message': 'Expired Data', 'tracing_id': '', "
            "'schema': '" + schema + "', "
            "'provider_type': '" + provider + "', "
            "'provider_uuid': " + str(None) + ", "
            "'simulate': " + str(simulate) + ", "
            "'removed_data': " + str(expected_results) + "}"
        )

        # disable logging override set in masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs("masu.processor._tasks.remove_expired") as logger:
            remove_expired_data(schema_name=schema, provider=provider, simulate=simulate)

            self.assertIn(expected_initial_remove_log, logger.output)
            self.assertIn(expected_expired_data_log, logger.output)

    @patch.object(ExpiredDataRemover, "remove")
    def test_remove_expired_data_no_simulate(self, fake_remover):
        """Test task."""
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        fake_remover.return_value = expected_results

        schema = self.schema
        provider = Provider.PROVIDER_AWS
        simulate = False

        expected_initial_remove_log = (
            "INFO:masu.processor._tasks.remove_expired:"
            "{'message': 'Remove expired data', 'tracing_id': '', "
            "'schema': '" + schema + "', "
            "'provider_type': '" + provider + "', "
            "'provider_uuid': " + str(None) + ", "
            "'simulate': " + str(simulate) + "}"
        )

        expected_expired_data_log = (
            "INFO:masu.processor._tasks.remove_expired:"
            "{'message': 'Expired Data', 'tracing_id': '', "
            "'schema': '" + schema + "', "
            "'provider_type': '" + provider + "', "
            "'provider_uuid': " + str(None) + ", "
            "'simulate': " + str(simulate) + ", "
            "'removed_data': " + str(expected_results) + "}"
        )

        # disable logging override set in masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs("masu.processor._tasks.remove_expired") as logger:
            remove_expired_data(schema_name=schema, provider=provider, simulate=simulate)

            self.assertIn(expected_initial_remove_log, logger.output)
            self.assertNotIn(expected_expired_data_log, logger.output)

    @patch.object(ExpiredDataRemover, "remove_expired_trino_partitions")
    def test_remove_expired_trino_partitions(self, fake_remover):
        """Test task."""
        expected_results = ["A"]
        fake_remover.return_value = expected_results

        # disable logging override set in masu/__init__.py
        logging.disable(logging.NOTSET)
        for simulate in [True, False]:
            with self.subTest(simulate=simulate):
                with self.assertLogs("masu.processor._tasks.remove_expired") as logger:
                    expected_initial_remove_log = (
                        "INFO:masu.processor._tasks.remove_expired:"
                        "{'message': 'Remove expired partitions', 'tracing_id': '', "
                        "'schema': '" + self.schema + "', "
                        "'provider_type': '" + Provider.PROVIDER_OCP + "', "
                        "'simulate': " + str(simulate) + "}"
                    )

                    expected_expired_data_log = (
                        "INFO:masu.processor._tasks.remove_expired:"
                        "{'message': 'Removed Partitions', 'tracing_id': '', "
                        "'schema': '" + self.schema + "', "
                        "'provider_type': '" + Provider.PROVIDER_OCP + "', "
                        "'simulate': " + str(simulate) + ", "
                        "'removed_data': " + str(expected_results) + "}"
                    )
                    remove_expired_trino_partitions(
                        schema_name=self.schema, provider_type=Provider.PROVIDER_OCP, simulate=simulate
                    )

                    self.assertIn(expected_initial_remove_log, logger.output)
                    if simulate:
                        self.assertNotIn(expected_expired_data_log, logger.output)
                    else:
                        self.assertIn(expected_expired_data_log, logger.output)


class TestUpdateSummaryTablesTask(MasuTestCase):
    """Test cases for Processor summary table Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up for the class."""
        super().setUpClass()
        cls.aws_tables = list(AWS_CUR_TABLE_MAP.values())
        cls.ocp_tables = list(OCP_REPORT_TABLE_MAP.values())
        cls.all_tables = list(AWS_CUR_TABLE_MAP.values()) + list(OCP_REPORT_TABLE_MAP.values())

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.aws_accessor = AWSReportDBAccessor(schema=self.schema)
        self.ocp_accessor = OCPReportDBAccessor(schema=self.schema)

        # Populate some line item data so that the summary tables
        # have something to pull from
        self.start_date = self.dh.today.replace(day=1)

    @patch("masu.util.common.trino_db.connect")
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportParquetSummaryUpdater._check_parquet_date_range"
    )
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    def test_update_summary_tables_ocp(
        self,
        mock_select_for_update,
        mock_cost_model,
        mock_charge_info,
        mock_chain,
        mock_task_cost_model,
        mock_cache,
        mock_date_check,
        mock_conn,
    ):
        """Test that the summary table task runs."""
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None
        infrastructure_rates = {
            "cpu_core_usage_per_hour": 1.5,
            "memory_gb_usage_per_hour": 2.5,
            "storage_gb_usage_per_month": 0.5,
        }
        markup = {}

        mock_cost_model.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_model.return_value.__enter__.return_value.supplementary_rates = {}
        mock_cost_model.return_value.__enter__.return_value.markup = markup
        mock_cost_model.return_value.__enter__.return_value.distribution_info = {
            "distribution_type": "cpu",
            "platform_cost": False,
            "worker_cost": False,
        }
        # We need to bypass the None check for cost model in update_cost_model_costs
        mock_task_cost_model.return_value.__enter__.return_value.cost_model = {}

        provider_type = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid

        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        mock_date_check.return_value = (start_date, end_date)

        update_summary_tables(
            self.schema, provider_type, provider_ocp_uuid, start_date, end_date, manifest_id=1, synchronous=True
        )
        update_cost_model_costs(
            schema_name=self.schema,
            provider_uuid=provider_ocp_uuid,
            start_date=start_date,
            end_date=end_date,
            synchronous=True,
        )

        usage_period_qry = self.ocp_accessor.get_usage_period_query_by_provider(self.ocp_provider.uuid)
        with schema_context(self.schema):
            cluster_id = usage_period_qry.first().cluster_id

            items = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                usage_start__lte=end_date,
                cluster_id=cluster_id,
                data_source="Pod",
                infrastructure_raw_cost__isnull=True,
            )
            for item in items:
                self.assertNotEqual(item.infrastructure_usage_cost.get("cpu"), 0)
                self.assertNotEqual(item.infrastructure_usage_cost.get("memory"), 0)

            items = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=cluster_id,
                data_source="Storage",
                infrastructure_raw_cost__isnull=True,
                cost_model_rate_type__isnull=True,
            )
            for item in items:
                self.assertIsNotNone(item.volume_request_storage_gigabyte_months)
                self.assertIsNotNone(item.persistentvolumeclaim_usage_gigabyte_months)

        mock_chain.return_value.apply_async.assert_called()

    @patch(
        "masu.processor.tasks.is_summary_processing_disabled",
        return_value=True,
    )
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_summary_tables_ocp_unleash_check(
        self, mock_cost_model, mock_charge_info, mock_chain, mock_task_cost_model, mock_cache, mock_unleash
    ):
        """Test that the summary table task runs."""

        provider_type = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid

        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        update_summary_tables(self.schema, provider_type, provider_ocp_uuid, start_date, end_date, synchronous=True)
        mock_chain.return_value.apply_async.assert_not_called()

    @patch("masu.util.common.trino_db.connect")
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportParquetSummaryUpdater._check_parquet_date_range"
    )
    @patch(
        "masu.processor.tasks.is_ocp_on_cloud_summary_disabled",
        return_value=True,
    )
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    def test_update_summary_tables_ocp_disabled_check(
        self,
        mock_select_for_update,
        mock_cost_model,
        mock_charge_info,
        mock_chain,
        mock_task_cost_model,
        mock_cache,
        mock_unleash,
        mock_date_check,
        mock_conn,
    ):
        """Test that the summary table task runs."""
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None
        provider_type = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid

        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        mock_date_check.return_value = (start_date, end_date)
        update_summary_tables(
            self.schema, provider_type, provider_ocp_uuid, start_date, end_date, manifest_id=1, synchronous=True
        )
        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.util.common.trino_db.connect")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.chain")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    def test_update_summary_tables_remove_expired_data(self, mock_select_for_update, mock_chain, *args):
        """Test that the update summary table task runs."""
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None

        provider_type = Provider.PROVIDER_AWS
        provider_aws_uuid = self.aws_provider_uuid
        start_date = self.dh.last_month_start - relativedelta.relativedelta(months=1)
        end_date = self.dh.today
        manifest_id = 1
        tracing_id = "1234"

        update_summary_tables(
            self.schema,
            provider_type,
            provider_aws_uuid,
            start_date,
            end_date,
            tracing_id=tracing_id,
            manifest_id=manifest_id,
            synchronous=True,
        )
        mock_chain.assert_called()
        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.util.common.trino_db.connect")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.chain")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_update_summary_tables_remove_expired_data_gcp(
        self, mock_infra_map, mock_select_for_update, mock_chain, *args
    ):
        """Test that the update summary table task runs for GCP."""
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None
        provider_type = Provider.PROVIDER_GCP
        start_date = self.dh.last_month_start - relativedelta.relativedelta(months=1)
        end_date = self.dh.today
        manifest_id = 1
        tracing_id = "1234"

        invoice_month = self.dh.gcp_find_invoice_months_in_date_range(start_date, end_date)[0]
        update_summary_tables(
            self.schema,
            provider_type,
            self.gcp_provider_uuid,
            start_date,
            end_date,
            tracing_id=tracing_id,
            manifest_id=manifest_id,
            synchronous=True,
            invoice_month=invoice_month,
        )
        mock_chain.assert_called()
        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.util.common.trino_db.connect")
    @patch("masu.processor.tasks.update_openshift_on_cloud")
    @patch("masu.processor.tasks.delete_openshift_on_cloud_data")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_update_summary_tables_ocp_on_cloud(
        self, mock_infra_map, mock_select_for_update, mock_accessor, mock_chain, mock_delete, mock_update, _
    ):
        """Test that we call delete tasks and ocp on cloud summary"""
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None

        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        manifest_id = 1
        tracing_id = "1234"
        updater = OCPCloudParquetReportSummaryUpdater(
            schema=self.schema, provider=self.aws_provider, manifest=manifest_id
        )
        mock_infra_map.return_value = updater.get_infra_map_from_providers()
        update_summary_tables(
            self.schema,
            self.aws_provider.type,
            self.aws_provider_uuid,
            start_date,
            end_date,
            manifest_id=manifest_id,
            tracing_id=tracing_id,
            synchronous=True,
        )
        mock_delete.si.assert_called()
        mock_update.si.assert_called()
        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.processor.tasks.update_summary_tables")
    def test_get_report_data_for_all_providers(self, mock_update):
        """Test GET report_data endpoint with provider_uuid=*."""
        start_date = date.today()
        update_all_summary_tables(start_date)
        mock_update.s.assert_called_with(ANY, ANY, ANY, str(start_date), ANY, queue_name=ANY)

    @patch("masu.processor.tasks.update_summary_tables")
    def test_get_report_data_for_provider_with_XL_queue(self, mock_update):
        """Test GET report_data endpoint with provider and XL queue"""
        start_date = date.today()
        with patch("masu.processor.tasks.get_customer_queue", return_value=SummaryQueue.XL):
            update_all_summary_tables(start_date)
            mock_update.s.return_value.apply_async.assert_called_with(queue=SummaryQueue.XL)

    @patch("masu.processor.tasks.connection")
    def test_autovacuum_tune_schema_default_table(self, mock_conn):
        """Test that the autovacuum tuning runs."""
        logging.disable(logging.NOTSET)

        # Make sure that the AUTOVACUUM_TUNING environment variable is unset!
        if "AUTOVACUUM_TUNING" in os.environ:
            del os.environ["AUTOVACUUM_TUNING"]

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 20000000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model set (autovacuum_vacuum_scale_factor = 0.01);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 2000000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model set (autovacuum_vacuum_scale_factor = 0.02);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 200000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model set (autovacuum_vacuum_scale_factor = 0.05);"
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
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model reset (autovacuum_vacuum_scale_factor);"
        )
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
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model "
            "set (autovacuum_vacuum_scale_factor = 0.0001);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 2000000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model set (autovacuum_vacuum_scale_factor = 0.004);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("cost_model", 200000, {})]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model set (autovacuum_vacuum_scale_factor = 0.011);"
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
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model reset (autovacuum_vacuum_scale_factor);"
        )
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
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model set (autovacuum_vacuum_scale_factor = 0.05);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

    @patch("masu.processor.tasks.connection")
    def test_autovacuum_tune_schema_invalid_setting(self, mock_conn):
        """Test that the autovacuum tuning runs."""
        logging.disable(logging.NOTSET)

        # Make sure that the AUTOVACUUM_TUNING environment variable is unset!
        if "AUTOVACUUM_TUNING" in os.environ:
            del os.environ["AUTOVACUUM_TUNING"]

        # This invalid setting should be treated as though there was no setting
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("cost_model", 20000000, {"autovacuum_vacuum_scale_factor": ""})
        ]
        expected = (
            "INFO:masu.processor.tasks:ALTER TABLE org1234567.cost_model set (autovacuum_vacuum_scale_factor = 0.01);"
        )
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            autovacuum_tune_schema(self.schema)
            self.assertIn(expected, logger.output)

    def test_autovacuum_tune_schema_normalize(self):
        """Test that the autovacuum tuning runs."""
        test_matrix = [
            {"table_options": None, "expected": {}},
            {"table_options": "{}", "expected": {}},
            {"table_options": {"foo": "bar"}, "expected": {"foo": "bar"}},
        ]
        for test in test_matrix:
            self.assertEqual(normalize_table_options(test.get("table_options")), test.get("expected"))

    @patch("masu.processor.tasks.CostUsageReportStatus.objects")
    def test_record_report_status(self, mock_stats):
        mock_stats.filter.return_value.first.return_value = mock_stats
        mock_stats.completed_datetime = True
        manifest_id = 1
        file_name = "testfile.csv"
        request_id = 3
        already_processed = record_report_status(manifest_id, file_name, request_id)
        self.assertTrue(already_processed)

        mock_stats.completed_datetime = False
        already_processed = record_report_status(manifest_id, file_name, request_id)
        self.assertFalse(already_processed)

    def test_record_all_manifest_files(self):
        """Test that file list is saved in CostUsageReportStatus."""
        files_list = ["file1.csv", "file2.csv", "file3.csv"]
        manifest_id = 1
        tracing_id = "1234"
        record_all_manifest_files(manifest_id, files_list, tracing_id)

        for report_file in files_list:
            CostUsageReportStatus.objects.filter(report_name=report_file).exists()

    def test_record_all_manifest_files_concurrent_writes(self):
        """Test that file list is saved in CostUsageReportStatus race condition."""
        files_list = ["file1.csv", "file2.csv", "file3.csv"]
        manifest_id = 1
        tracing_id = "1234"
        record_all_manifest_files(manifest_id, files_list, tracing_id)
        with patch("masu.processor.tasks.CostUsageReportStatus.objects") as mock_stats:
            mock_stats.get_or_create.side_effect = IntegrityError
            record_all_manifest_files(manifest_id, files_list, tracing_id)

        for report_file in files_list:
            CostUsageReportStatus.objects.filter(report_name=report_file).exists()
            self.assertEqual(CostUsageReportStatus.objects.filter(report_name=report_file).count(), 1)

    @patch("masu.processor.tasks.ReportSummaryUpdater.update_openshift_on_cloud_summary_tables")
    @patch("masu.processor.tasks.update_cost_model_costs.s")
    @patch("masu.processor.tasks.validate_daily_data.s")
    def test_update_openshift_on_cloud(self, mock_data_validator, mock_cost_updater, mock_updater):
        """Test that this task runs."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.today.date()

        update_openshift_on_cloud(
            self.schema,
            self.ocp_on_aws_ocp_provider.uuid,
            self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
            synchronous=True,
        )

        mock_updater.side_effect = ReportSummaryUpdaterCloudError
        with self.assertRaises(ReportSummaryUpdaterCloudError):
            update_openshift_on_cloud(
                self.schema,
                self.ocp_on_aws_ocp_provider.uuid,
                self.aws_provider_uuid,
                Provider.PROVIDER_AWS,
                start_date,
                end_date,
                synchronous=True,
            )

    @patch(
        "masu.processor.tasks.is_ocp_on_cloud_summary_disabled",
        return_value=True,
    )
    def test_update_openshift_on_cloud_unleash_gated(self, _):
        """Test that this task runs."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.today.date()

        expecte_msg = f"OCP on Cloud summary disabled for {self.schema}."
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            update_openshift_on_cloud(
                self.schema,
                self.ocp_on_aws_ocp_provider.uuid,
                self.aws_provider_uuid,
                Provider.PROVIDER_AWS,
                start_date,
                end_date,
                synchronous=True,
            )

            statement_found = False
            for log in logger.output:
                if expecte_msg in log:
                    statement_found = True
            self.assertTrue(statement_found)

    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_update_summary_tables(self, mock_infra_map, mock_select_for_update, mock_updater, mock_complete):
        """Test that this task runs."""
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.today.date()
        mock_updater.return_value = (start_date, end_date)

        update_summary_tables(
            self.schema,
            Provider.PROVIDER_AWS,
            self.aws_provider_uuid,
            str(start_date),
            end_date,
            synchronous=True,
        )

        mock_updater.side_effect = ReportSummaryUpdaterError
        with self.assertRaises(ReportSummaryUpdaterError):
            update_summary_tables(
                self.schema,
                Provider.PROVIDER_AWS,
                self.aws_provider_uuid,
                start_date,
                end_date,
                synchronous=True,
            )


class TestMarkManifestCompleteTask(MasuTestCase):
    """Test cases for Processor summary table Celery tasks."""

    def test_mark_manifest_complete(self):
        """Test that we mark a manifest complete."""
        provider = self.ocp_provider
        initial_update_time = provider.data_updated_timestamp
        start = self.dh.this_month_start
        manifest = CostUsageReportManifest(
            **{
                "assembly_id": "1",
                "provider_id": str(provider.uuid),
                "billing_period_start_datetime": start,
                "num_total_files": 1,
            }
        )
        manifest.save()
        mark_manifest_complete(
            self.schema, provider.type, manifest_list=[manifest.id], provider_uuid=str(provider.uuid), tracing_id=1
        )

        provider = Provider.objects.filter(uuid=self.ocp_provider.uuid).first()
        manifest = CostUsageReportManifest.objects.filter(id=manifest.id).first()
        self.assertGreater(provider.data_updated_timestamp, initial_update_time)
        self.assertIsNotNone(manifest.completed_datetime)

    def test_mark_manifest_complete_no_manifest(self):
        """Test that we mark a manifest complete."""
        provider = self.ocp_provider
        initial_update_time = provider.data_updated_timestamp
        mark_manifest_complete(
            self.schema, provider.type, manifest_list=None, provider_uuid=str(provider.uuid), tracing_id=1
        )

        provider = Provider.objects.filter(uuid=self.ocp_provider.uuid).first()
        self.assertGreater(provider.data_updated_timestamp, initial_update_time)

    def test_mark_ingress_report_complete(self):
        """Test that we mark ingress reports complete."""
        provider = self.aws_provider
        start = self.dh.this_month_start
        manifest = CostUsageReportManifest(
            **{
                "assembly_id": "1",
                "provider_id": str(provider.uuid),
                "billing_period_start_datetime": start,
                "num_total_files": 1,
            }
        )
        manifest.save()
        with schema_context(self.schema):
            ingress_report = IngressReports(
                **{
                    "uuid": str(uuid4()),
                    "created_timestamp": start,
                    "completed_timestamp": None,
                    "reports_list": ["test"],
                    "source": provider,
                }
            )
            ingress_report.save()
        mark_manifest_complete(
            self.schema,
            provider.type,
            manifest_list=[manifest.id],
            provider_uuid=str(provider.uuid),
            ingress_report_uuid=ingress_report.uuid,
            tracing_id=1,
        )

        with schema_context(self.schema):
            ingress_report.refresh_from_db()
            self.assertIsNotNone(ingress_report.completed_timestamp)


@override_settings(HOSTNAME="kokuworker")
class TestWorkerCacheThrottling(MasuTestCase):
    """Tests for tasks that use the worker cache."""

    def single_task_is_running(self, task_name, task_args=None):
        """Check for a single task key in the cache."""
        cache = caches[CacheEnum.worker]
        cache_str = create_single_task_cache_key(task_name, task_args)
        return bool(cache.get(cache_str))

    def lock_single_task(self, task_name, task_args=None, timeout=None):
        """Add a cache entry for a single task to lock a specific task."""
        cache = caches[CacheEnum.worker]
        cache_str = create_single_task_cache_key(task_name, task_args)
        cache.add(cache_str, "kokuworker", 3)

    @patch("masu.processor.tasks.group")
    @patch("masu.processor.tasks.update_summary_tables.s")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_update_summary_tables_worker_throttled(
        self,
        mock_infra_map,
        mock_select_for_update,
        mock_inspect,
        mock_lock,
        mock_release,
        mock_update_cost,
        mock_complete,
        mock_chain,
        mock_summary,
        mock_delay,
        mock_ocp_on_cloud,
    ):
        """Test that the worker cache is used."""
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        task_name = "masu.processor.tasks.update_summary_tables"
        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        cache_args = [self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, str(start_date.strftime("%Y-%m"))]
        mock_lock.side_effect = self.lock_single_task
        updater = OCPCloudParquetReportSummaryUpdater(schema=self.schema, provider=self.aws_provider, manifest=None)
        mock_infra_map.return_value = updater.get_infra_map_from_providers()

        mock_summary.return_value = start_date, end_date
        update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
        mock_delay.assert_not_called()
        update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
        mock_delay.assert_called()
        self.assertTrue(self.single_task_is_running(task_name, cache_args))
        # Let the cache entry expire
        time.sleep(3)
        self.assertFalse(self.single_task_is_running(task_name, cache_args))

        with patch("masu.processor.tasks.get_customer_queue", return_value=SummaryQueue.XL):
            with patch("masu.processor.tasks.rate_limit_tasks") as mock_rate_limit:
                mock_rate_limit.return_value = False
                mock_delay.reset_mock()
                update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
                mock_delay.assert_not_called()

                mock_rate_limit.return_value = True

                update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
                mock_delay.assert_called()

    @patch("masu.processor.tasks.update_summary_tables.s")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_update_summary_tables_worker_error(
        self,
        mock_inspect,
        mock_lock,
        mock_release,
        mock_update_cost,
        mock_complete,
        mock_chain,
        mock_summary,
        mock_delay,
    ):
        """Test that the worker cache is used."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        task_name = "masu.processor.tasks.update_summary_tables"
        cache_args = [self.schema]

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        mock_summary.side_effect = ReportProcessorError
        with self.assertRaises(ReportProcessorError):
            update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
            mock_delay.assert_not_called()
            self.assertFalse(self.single_task_is_running(task_name, cache_args))

    @patch("masu.processor.tasks.update_summary_tables.s")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    def test_update_summary_tables_cloud_summary_error(
        self,
        mock_select_for_update,
        mock_inspect,
        mock_lock,
        mock_release,
        mock_update_cost,
        mock_complete,
        mock_chain,
        mock_summary,
        mock_delay,
    ):
        """Test that the update_summary_table cloud exception is caught."""
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        mock_summary.side_effect = ReportSummaryUpdaterCloudError
        with self.assertRaises(ReportSummaryUpdaterCloudError):
            update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)

    @patch("masu.processor.tasks.update_summary_tables.s")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.util.common.CostUsageReportManifest")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    def test_update_summary_tables_provider_not_found_error(
        self,
        mock_select_for_update,
        mock_manifest,
        mock_inspect,
        mock_lock,
        mock_release,
        mock_update_cost,
        mock_complete,
        mock_chain,
        mock_summary,
        mock_delay,
    ):
        """Test that the update_summary_table provider not found exception is caught."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None
        mock_summary.side_effect = ReportSummaryUpdaterProviderNotFoundError
        expected = "halting processing"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            update_summary_tables(self.schema, Provider.PROVIDER_AWS, str(uuid4()), start_date, end_date)
            statement_found = any(expected in log for log in logger.output)
            self.assertTrue(statement_found)

    @patch("masu.util.common.CostUsageReportManifest")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    def test_update_openshift_on_cloud_provider_not_found_error(
        self,
        mock_select_for_update,
        mock_inspect,
        *args,
    ):
        """Test that the update_summary_table provider not found exception is caught."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None
        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        expected = "halting processing"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            update_openshift_on_cloud(
                self.schema,
                str(uuid4()),
                str(uuid4()),
                Provider.PROVIDER_AWS,
                start_date,
                end_date,
            )
            statement_found = any(expected in log for log in logger.output)
            self.assertTrue(statement_found)

    @skip("cost model calcs are taking longer with the conversion to partables. This test needs a rethink.")
    @patch("masu.processor.tasks.update_cost_model_costs.s")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_update_cost_model_costs_throttled(self, mock_inspect, mock_lock, mock_release, mock_delay):
        """Test that refresh materialized views runs with cache lock."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        mock_lock.side_effect = self.lock_single_task

        start_date = self.dh.last_month_start - relativedelta.relativedelta(months=1)
        end_date = self.dh.today
        expected_start_date = start_date.strftime("%Y-%m-%d")
        expected_end_date = end_date.strftime("%Y-%m-%d")
        task_name = "masu.processor.tasks.update_cost_model_costs"
        cache_args = [self.schema, self.aws_provider_uuid, expected_start_date, expected_end_date]

        manifest_dict = {
            "assembly_id": "12345",
            "billing_period_start_datetime": self.dh.today,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
        }
        self.baker.make("CostUsageReportManifest", **manifest_dict)

        update_cost_model_costs(self.schema, self.aws_provider_uuid, expected_start_date, expected_end_date)
        mock_delay.assert_not_called()
        update_cost_model_costs(self.schema, self.aws_provider_uuid, expected_start_date, expected_end_date)
        mock_delay.assert_called()
        self.assertTrue(self.single_task_is_running(task_name, cache_args))
        # Let the cache entry expire
        time.sleep(3)
        self.assertFalse(self.single_task_is_running(task_name, cache_args))

    @patch("masu.processor.tasks.CostModelCostUpdater")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_update_cost_model_costs_error(self, mock_inspect, mock_lock, mock_release, mock_updater):
        """Test that refresh materialized views runs with cache lock."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        start_date = self.dh.last_month_start - relativedelta.relativedelta(months=1)
        end_date = self.dh.today
        expected_start_date = start_date.strftime("%Y-%m-%d")
        expected_end_date = end_date.strftime("%Y-%m-%d")
        task_name = "masu.processor.tasks.update_cost_model_costs"
        cache_args = [self.schema, self.aws_provider_uuid, expected_start_date, expected_end_date]

        mock_updater.side_effect = ReportProcessorError
        with self.assertRaises(ReportProcessorError):
            update_cost_model_costs(self.schema, self.aws_provider_uuid, expected_start_date, expected_end_date)
            self.assertFalse(self.single_task_is_running(task_name, cache_args))

    @patch("masu.processor.tasks.ReportSummaryUpdater.update_openshift_on_cloud_summary_tables")
    @patch("masu.processor.tasks.update_openshift_on_cloud.s")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks.update_cost_model_costs.s")
    @patch("masu.processor.tasks.validate_daily_data.s")
    def test_update_openshift_on_cloud_throttled(
        self, mock_data_validator, mock_model_update, mock_inspect, mock_lock, mock_release, mock_delay, mock_update
    ):
        """Test that refresh materialized views runs with cache lock."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.today.date()

        mock_lock.side_effect = self.lock_single_task
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}

        task_name = "masu.processor.tasks.update_openshift_on_cloud"
        cache_args = [
            self.schema,
            self.aws_provider_uuid,
            self.ocpaws_provider_uuid,
            str(start_date.strftime("%Y-%m")),
        ]

        manifest_dict = {
            "assembly_id": "12345",
            "billing_period_start_datetime": self.dh.today,
            "num_total_files": 2,
            "provider_id": self.aws_provider_uuid,
        }
        self.baker.make("CostUsageReportManifest", **manifest_dict)

        update_openshift_on_cloud(
            self.schema,
            self.ocpaws_provider_uuid,
            self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
        )
        mock_model_update.assert_called_once()
        mock_delay.assert_not_called()
        update_openshift_on_cloud(
            self.schema,
            self.ocpaws_provider_uuid,
            self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
        )
        update_openshift_on_cloud(
            self.schema,
            self.ocpaws_provider_uuid,
            self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
        )
        mock_delay.assert_called()
        self.assertTrue(self.single_task_is_running(task_name, cache_args))
        # Let the cache entry expire
        time.sleep(3)
        self.assertFalse(self.single_task_is_running(task_name, cache_args))

        with patch("masu.processor.tasks.get_customer_queue", return_value=SummaryQueue.XL):
            with patch("masu.processor.tasks.rate_limit_tasks") as mock_rate_limit:
                mock_rate_limit.return_value = False
                mock_delay.reset_mock()
                update_openshift_on_cloud(
                    self.schema,
                    self.ocpaws_provider_uuid,
                    self.aws_provider_uuid,
                    Provider.PROVIDER_AWS,
                    start_date,
                    end_date,
                )
                mock_delay.assert_not_called()

                mock_rate_limit.return_value = True

                update_openshift_on_cloud(
                    self.schema,
                    self.ocpaws_provider_uuid,
                    self.aws_provider_uuid,
                    Provider.PROVIDER_AWS,
                    start_date,
                    end_date,
                )
                mock_delay.assert_called()

    @patch("masu.processor.tasks.chain")
    def test_unleash_disable_source(self, mock_chain):
        """Test unleash flag to disable processing by source_uuid."""
        provider_type = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid

        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        with patch("masu.processor.tasks.is_source_disabled") as disable_source:
            disable_source.return_value = True
            update_summary_tables(
                self.schema, provider_type, provider_ocp_uuid, start_date, end_date, synchronous=True
            )
            mock_chain.return_value.apply_async.assert_not_called()


class TestRemoveStaleTenants(MasuTestCase):
    def setUp(self):
        """Set up middleware tests."""
        super().setUp()
        request = self.request_context["request"]
        request.path = "/api/v1/tags/aws/"

    @patch("koku.middleware.KokuTenantMiddleware.tenant_cache", TTLCache(5, 10))
    def test_remove_stale_tenant(self):
        """Test removal of stale tenants that are older than two weeks"""
        days = 14
        initial_date_updated = self.customer.date_updated
        self.assertIsNotNone(initial_date_updated)
        with schema_context("public"):
            mock_request = self.request_context["request"]
            mock_get_response = Mock()
            middleware = KokuTenantMiddleware(mock_get_response)
            middleware._get_tenant(mock_request)
            self.assertNotEqual(KokuTenantMiddleware.tenant_cache.currsize, 0)
            remove_stale_tenants()  # Check that it is not clearing the cache unless removing
            self.assertNotEqual(KokuTenantMiddleware.tenant_cache.currsize, 0)
            self.customer.date_updated = self.dh.n_days_ago(self.customer.date_updated, days)
            self.customer.save()
            before_len = Tenant.objects.count()
            remove_stale_tenants()
            after_len = Tenant.objects.count()
            self.assertGreater(before_len, after_len)
            self.assertEqual(KokuTenantMiddleware.tenant_cache.currsize, 0)
