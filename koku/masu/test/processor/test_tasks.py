#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the download task."""
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
from unittest.mock import call
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
from tenant_schemas.utils import schema_context

from api.iam.models import Tenant
from api.models import Provider
from api.utils import DateHelper
from koku.middleware import KokuTenantMiddleware
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.exceptions import MasuProcessingError
from masu.exceptions import MasuProviderError
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
from masu.external.report_downloader import ReportDownloaderError
from masu.processor._tasks.download import _get_report_files
from masu.processor._tasks.process import _process_report_file
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.report_processor import ReportProcessorError
from masu.processor.report_summary_updater import ReportSummaryUpdaterCloudError
from masu.processor.report_summary_updater import ReportSummaryUpdaterError
from masu.processor.report_summary_updater import ReportSummaryUpdaterProviderNotFoundError
from masu.processor.tasks import autovacuum_tune_schema
from masu.processor.tasks import get_report_files
from masu.processor.tasks import mark_manifest_complete
from masu.processor.tasks import MARK_MANIFEST_COMPLETE_QUEUE
from masu.processor.tasks import normalize_table_options
from masu.processor.tasks import process_openshift_on_cloud
from masu.processor.tasks import record_all_manifest_files
from masu.processor.tasks import record_report_status
from masu.processor.tasks import remove_expired_data
from masu.processor.tasks import remove_stale_tenants
from masu.processor.tasks import summarize_reports
from masu.processor.tasks import update_all_summary_tables
from masu.processor.tasks import update_cost_model_costs
from masu.processor.tasks import UPDATE_COST_MODEL_COSTS_QUEUE
from masu.processor.tasks import update_openshift_on_cloud
from masu.processor.tasks import update_summary_tables
from masu.processor.tasks import vacuum_schema
from masu.processor.worker_cache import create_single_task_cache_key
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from masu.test.external.downloader.aws import fake_arn
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


LOG = logging.getLogger(__name__)


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
            report_context={},
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
                report_month=DateHelper().today,
                provider_uuid=self.aws_provider_uuid,
                billing_source=self.fake.word(),
                report_context={},
            )
            statement_found = any(expected in log for log in logger.output)
            self.assertTrue(statement_found)

        shutil.rmtree(Config.TMP_DIR, ignore_errors=True)

    @patch("masu.processor._tasks.download.ReportDownloader", return_value=FakeDownloader)
    def test_disk_status_logging_no_dir(self, fake_downloader):
        """Test task for logging when temp directory does not exist."""
        logging.disable(logging.NOTSET)

        Config.PVC_DIR = "/this/path/does/not/exist"

        account = fake_arn(service="iam", generate_account_id=True)
        expected = "Unable to find" + f" available disk space. {Config.PVC_DIR} does not exist"
        with self.assertLogs("masu.processor._tasks.download", level="INFO") as logger:
            _get_report_files(
                Mock(),
                customer_name=self.fake.word(),
                authentication=account,
                provider_type=Provider.PROVIDER_AWS,
                report_month=DateHelper().today,
                provider_uuid=self.aws_provider_uuid,
                billing_source=self.fake.word(),
                report_context={},
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
                report_month=DateHelper().today,
                provider_uuid=uuid4(),
                billing_source=self.fake.word(),
                report_context={},
            )


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
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(DateHelper().today),
            "provider_uuid": provider_uuid,
        }

        mock_proc = mock_processor()
        mock_stats_acc = mock_stats_accessor().__enter__()
        mock_manifest_acc = mock_manifest_accessor().__enter__()
        mock_provider_acc = mock_provider_accessor().__enter__()
        mock_provider_acc.get_setup_complete.return_value = False

        _process_report_file(schema_name, provider, report_dict)

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
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(DateHelper().today),
            "provider_uuid": provider_uuid,
        }

        mock_proc = mock_processor()
        mock_stats_acc = mock_stats_accessor().__enter__()
        mock_manifest_acc = mock_manifest_accessor().__enter__()
        mock_provider_acc = mock_provider_accessor().__enter__()
        mock_provider_acc.get_setup_complete.return_value = True

        _process_report_file(schema_name, provider, report_dict)

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
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(DateHelper().today),
            "provider_uuid": provider_uuid,
        }

        mock_processor.side_effect = ReportProcessorError("mock error")
        mock_stats_acc = mock_stats_accessor().__enter__()

        with self.assertRaises(ReportProcessorError):
            _process_report_file(schema_name, provider, report_dict)

        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_not_called()
        shutil.rmtree(report_dir)

    @patch("masu.processor._tasks.process.ReportProcessor")
    @patch("masu.processor._tasks.process.ReportStatsDBAccessor")
    def test_process_file_not_implemented_exception(self, mock_stats_accessor, mock_processor):
        """Test the process_report_file functionality when exception is thrown."""
        report_dir = tempfile.mkdtemp()
        path = "{}/{}".format(report_dir, "file1.csv")
        schema_name = self.schema
        provider = Provider.PROVIDER_AWS
        provider_uuid = self.aws_provider_uuid
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(DateHelper().today),
            "provider_uuid": provider_uuid,
        }

        mock_processor.side_effect = NotImplementedError("mock error")
        mock_stats_acc = mock_stats_accessor().__enter__()

        with self.assertRaises(NotImplementedError):
            _process_report_file(schema_name, provider, report_dict)

        mock_stats_acc.log_last_started_datetime.assert_called()
        mock_stats_acc.log_last_completed_datetime.assert_called()
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
        report_dict = {
            "file": path,
            "compression": "gzip",
            "start_date": str(DateHelper().today),
            "provider_uuid": provider_uuid,
        }

        mock_proc = mock_processor()
        mock_stats_acc = mock_stats_accessor().__enter__()
        mock_manifest_acc = mock_manifest_accessor().__enter__()

        _process_report_file(schema_name, provider, report_dict)

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
        providers = [
            {"type": Provider.PROVIDER_OCP, "uuid": self.ocp_test_provider_uuid},
            {"type": Provider.PROVIDER_GCP, "uuid": self.gcp_test_provider_uuid},
        ]
        for provider_dict in providers:
            invoice_month = DateHelper().gcp_find_invoice_months_in_date_range(
                DateHelper().yesterday, DateHelper().today
            )[0]
            with self.subTest(provider_dict=provider_dict):
                mock_update_summary.s = Mock()
                report_meta = {}
                report_meta["start_date"] = str(DateHelper().today)
                report_meta["schema_name"] = self.schema
                report_meta["provider_type"] = Provider.PROVIDER_OCP
                report_meta["provider_uuid"] = self.ocp_test_provider_uuid
                report_meta["manifest_id"] = 1
                report_meta["start"] = str(DateHelper().yesterday)
                report_meta["end"] = str(DateHelper().today)
                if provider_dict.get("type") == Provider.PROVIDER_GCP:
                    report_meta["invoice_month"] = invoice_month

                # add a report with start/end dates specified
                report2_meta = {}
                report2_meta["start_date"] = str(DateHelper().today)
                report2_meta["schema_name"] = self.schema
                report2_meta["provider_type"] = Provider.PROVIDER_OCP
                report2_meta["provider_uuid"] = self.ocp_test_provider_uuid
                report2_meta["manifest_id"] = 2
                report2_meta["start"] = str(DateHelper().yesterday)
                report2_meta["end"] = str(DateHelper().today)
                if provider_dict.get("type") == Provider.PROVIDER_GCP:
                    report_meta["invoice_month"] = invoice_month

                reports_to_summarize = [report_meta, report2_meta]

                summarize_reports(reports_to_summarize)
                mock_update_summary.s.assert_called()

    @patch("masu.processor.tasks.update_summary_tables")
    def test_summarize_reports_processing_list_with_none(self, mock_update_summary):
        """Test that the summarize_reports task is called when a processing list when a None provided."""
        mock_update_summary.s = Mock()

        report_meta = {}
        report_meta["start_date"] = str(DateHelper().today)
        report_meta["schema_name"] = self.schema
        report_meta["provider_type"] = Provider.PROVIDER_OCP
        report_meta["provider_uuid"] = self.ocp_test_provider_uuid
        report_meta["manifest_id"] = 1
        reports_to_summarize = [report_meta, None]

        summarize_reports(reports_to_summarize)
        mock_update_summary.s.assert_called()

    @patch("masu.processor.tasks.update_summary_tables")
    def test_summarize_reports_processing_list_only_none(self, mock_update_summary):
        """Test that the summarize_reports task is called when a processing list with None provided."""
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
        cls.today = DateHelper().today
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
            "report_month": DateHelper().today,
            "report_context": {"current_file": f"/my/{self.test_assembly_id}/koku-1.csv.gz"},
        }
        self.get_report_args_gcp = {
            "customer_name": self.schema,
            "authentication": self.gcp_provider.authentication.credentials,
            "provider_type": Provider.PROVIDER_GCP_LOCAL,
            "schema_name": self.schema,
            "billing_source": self.gcp_provider.billing_source.data_source,
            "provider_uuid": self.gcp_provider_uuid,
            "report_month": DateHelper().today,
            "report_context": {"current_file": f"/my/{self.test_assembly_id}/koku-1.csv.gz"},
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
        expected_log = "No report to be processed:"
        with patch("masu.processor.tasks._get_report_files", return_value=None) as mock_get_files:
            with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
                get_report_files(**self.get_report_args)
                mock_get_files.assert_called()
                mock_cache_remove.assert_called()
                mock_process_files.assert_not_called()
                self.assertIn(expected_log, logger.output[0])

    @patch("masu.processor.tasks.WorkerCache.remove_task_from_cache")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks._get_report_files")
    @patch("masu.processor.tasks._process_report_file")
    def test_get_report_files_report_dict_invoice_month(
        self, mock_process_files, mock_get_files, mock_inspect, mock_cache_remove
    ):
        """Test raising download exception is handled."""
        expected_log = "Invoice_month: 202201"
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

    @patch("masu.processor.tasks.OCPCloudParquetReportProcessor.process")
    @patch("masu.processor.tasks.remove_files_not_in_set_from_s3_bucket")
    @patch("masu.processor.tasks.execute_trino_query")
    def test_process_openshift_on_cloud(self, mock_trino, mock_s3_delete, mock_process):
        """Test the process_openshift_on_cloud task."""
        tracing_id = uuid4()
        month_start = DateHelper().this_month_start
        year = month_start.strftime("%Y")
        month = month_start.strftime("%m")
        mock_trino.return_value = ([[1000]], ["column_name"])
        process_openshift_on_cloud(self.schema, self.aws_provider_uuid, month_start, tracing_id=tracing_id)

        expected_count_sql = (
            "SELECT count(*) FROM aws_line_items_daily "
            f"WHERE source='{self.aws_provider_uuid}' AND year='{year}'"
            f" AND month='{month}'"
        )

        expected_fetch_sql = (
            "SELECT * FROM aws_line_items_daily "
            f"WHERE source='{self.aws_provider_uuid}' AND year='{year}'"
            f" AND month='{month}' OFFSET 0 LIMIT {settings.PARQUET_PROCESSING_BATCH_SIZE}"
        )
        expected_calls = [
            call(self.schema, expected_count_sql),
            call(self.schema, expected_fetch_sql),
        ]
        mock_trino.assert_has_calls(expected_calls, any_order=True)
        mock_s3_delete.assert_called()
        mock_process.assert_called()


class TestRemoveExpiredDataTasks(MasuTestCase):
    """Test cases for Processor Celery tasks."""

    @patch.object(ExpiredDataRemover, "remove")
    def test_remove_expired_data(self, fake_remover):
        """Test task."""
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        fake_remover.return_value = expected_results

        expected = "INFO:masu.processor._tasks.remove_expired:Expired Data:\n {}"

        # disable logging override set in masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs("masu.processor._tasks.remove_expired") as logger:
            remove_expired_data(schema_name=self.schema, provider=Provider.PROVIDER_AWS, simulate=True)
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

    @patch("masu.util.common.trino_db.connect")
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportParquetSummaryUpdater._check_parquet_date_range"
    )
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks.CostModelDBAccessor")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_summary_tables_ocp(
        self,
        mock_cost_model,
        mock_charge_info,
        mock_chain,
        mock_task_cost_model,
        mock_cache,
        mock_date_check,
        mock_conn,
    ):
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
        mock_cost_model.return_value.__enter__.return_value.distribution = "cpu"
        # We need to bypass the None check for cost model in update_cost_model_costs
        mock_task_cost_model.return_value.__enter__.return_value.cost_model = {}

        provider = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid

        start_date = DateHelper().last_month_start
        end_date = DateHelper().last_month_end
        mock_date_check.return_value = (start_date, end_date)

        update_summary_tables(self.schema, provider, provider_ocp_uuid, start_date, end_date, synchronous=True)
        update_cost_model_costs(
            schema_name=self.schema,
            provider_uuid=provider_ocp_uuid,
            start_date=start_date,
            end_date=end_date,
            synchronous=True,
        )

        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        with ProviderDBAccessor(provider_ocp_uuid) as provider_accessor:
            provider_obj = provider_accessor.get_provider()

        usage_period_qry = self.ocp_accessor.get_usage_period_query_by_provider(provider_obj.uuid)
        with schema_context(self.schema):
            cluster_id = usage_period_qry.first().cluster_id

            items = self.ocp_accessor._get_db_obj_query(table_name).filter(
                usage_start__gte=start_date,
                usage_start__lte=end_date,
                cluster_id=cluster_id,
                data_source="Pod",
                infrastructure_raw_cost__isnull=True,
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
        "masu.processor.tasks.disable_summary_processing",
        return_value=True,
    )
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks.CostModelDBAccessor")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_summary_tables_ocp_unleash_check(
        self, mock_cost_model, mock_charge_info, mock_chain, mock_task_cost_model, mock_cache, mock_unleash
    ):
        """Test that the summary table task runs."""

        provider = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid

        start_date = DateHelper().last_month_start
        end_date = DateHelper().last_month_end
        update_summary_tables(self.schema, provider, provider_ocp_uuid, start_date, end_date, synchronous=True)
        mock_chain.return_value.apply_async.assert_not_called()

    @patch("masu.util.common.trino_db.connect")
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportParquetSummaryUpdater._check_parquet_date_range"
    )
    @patch(
        "masu.processor.tasks.disable_ocp_on_cloud_summary",
        return_value=True,
    )
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.tasks.CostModelDBAccessor")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_summary_tables_ocp_disabled_check(
        self,
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

        provider = Provider.PROVIDER_OCP
        provider_ocp_uuid = self.ocp_test_provider_uuid

        start_date = DateHelper().last_month_start
        end_date = DateHelper().last_month_end
        mock_date_check.return_value = (start_date, end_date)
        update_summary_tables(self.schema, provider, provider_ocp_uuid, start_date, end_date, synchronous=True)
        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.util.common.trino_db.connect")
    @patch(
        "masu.processor.ocp.ocp_report_parquet_summary_updater.OCPReportParquetSummaryUpdater._check_parquet_date_range"
    )
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.CostModelDBAccessor")
    def test_update_summary_tables_remove_expired_data(self, mock_accessor, mock_chain, mock_date_check, mock_conn):
        """Test that the update summary table task runs."""

        # COST-444: We use start & end date based off manifest
        provider = Provider.PROVIDER_AWS
        provider_aws_uuid = self.aws_provider_uuid
        start_date = DateHelper().last_month_start - relativedelta.relativedelta(months=1)
        end_date = DateHelper().today
        manifest_id = 1
        tracing_id = "1234"
        mock_date_check.return_value = (start_date, end_date)

        update_summary_tables(
            self.schema,
            provider,
            provider_aws_uuid,
            start_date,
            end_date,
            manifest_id,
            tracing_id=tracing_id,
            synchronous=True,
        )
        mock_chain.assert_called_once_with(
            mark_manifest_complete.s(
                self.schema,
                provider,
                provider_uuid=provider_aws_uuid,
                manifest_list=[manifest_id],
                tracing_id=tracing_id,
            ).set(queue=MARK_MANIFEST_COMPLETE_QUEUE)
        )
        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.CostModelDBAccessor")
    def test_update_summary_tables_remove_expired_data_gcp(self, mock_accessor, mock_chain):
        # COST-444: We use start & end date based off manifest
        provider = Provider.PROVIDER_GCP
        start_date = DateHelper().last_month_start - relativedelta.relativedelta(months=1)
        end_date = DateHelper().today
        manifest_id = 1
        tracing_id = "1234"

        invoice_month = DateHelper().gcp_find_invoice_months_in_date_range(start_date, end_date)[0]
        update_summary_tables(
            self.schema,
            provider,
            self.gcp_provider_uuid,
            start_date,
            end_date,
            manifest_id,
            tracing_id=tracing_id,
            synchronous=True,
            invoice_month=invoice_month,
        )
        mock_chain.assert_called_once_with(
            update_cost_model_costs.s(self.schema, self.gcp_provider_uuid, ANY, ANY, tracing_id=tracing_id).set(
                queue=UPDATE_COST_MODEL_COSTS_QUEUE
            )
            | mark_manifest_complete.si(
                self.schema,
                provider,
                provider_uuid=self.gcp_provider_uuid,
                manifest_list=[manifest_id],
                tracing_id=tracing_id,
            ).set(queue=MARK_MANIFEST_COMPLETE_QUEUE)
        )
        mock_chain.return_value.apply_async.assert_called()

    @patch("masu.processor.tasks.update_summary_tables")
    def test_get_report_data_for_all_providers(self, mock_update):
        """Test GET report_data endpoint with provider_uuid=*."""
        start_date = date.today()
        update_all_summary_tables(start_date)

        mock_update.s.assert_called_with(ANY, ANY, ANY, str(start_date), ANY, queue_name=ANY)

    @patch("masu.processor.tasks.connection")
    def test_vacuum_schema(self, mock_conn):
        """Test that the vacuum schema task runs."""
        logging.disable(logging.NOTSET)
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [("table",)]
        expected = "INFO:masu.processor.tasks:VACUUM ANALYZE org1234567.table"
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

    @patch("masu.processor.tasks.ReportStatsDBAccessor.get_last_completed_datetime")
    def test_record_report_status(self, mock_accessor):
        mock_accessor.return_value = True
        manifest_id = 1
        file_name = "testfile.csv"
        request_id = 3
        already_processed = record_report_status(manifest_id, file_name, request_id)
        self.assertTrue(already_processed)

        mock_accessor.return_value = False
        already_processed = record_report_status(manifest_id, file_name, request_id)
        self.assertFalse(already_processed)

    def test_record_all_manifest_files(self):
        """Test that file list is saved in ReportStatsDBAccessor."""
        files_list = ["file1.csv", "file2.csv", "file3.csv"]
        manifest_id = 1
        tracing_id = "1234"
        record_all_manifest_files(manifest_id, files_list, tracing_id)

        for report_file in files_list:
            CostUsageReportStatus.objects.filter(report_name=report_file).exists()

    def test_record_all_manifest_files_concurrent_writes(self):
        """Test that file list is saved in ReportStatsDBAccessor race condition."""
        files_list = ["file1.csv", "file2.csv", "file3.csv"]
        manifest_id = 1
        tracing_id = "1234"
        record_all_manifest_files(manifest_id, files_list, tracing_id)
        with patch.object(ReportStatsDBAccessor, "does_db_entry_exist", return_value=False):
            with patch.object(ReportStatsDBAccessor, "add", side_effect=IntegrityError):
                record_all_manifest_files(manifest_id, files_list, tracing_id)

        for report_file in files_list:
            CostUsageReportStatus.objects.filter(report_name=report_file).exists()

    @patch("masu.processor.tasks.ReportSummaryUpdater.update_openshift_on_cloud_summary_tables")
    def test_update_openshift_on_cloud(self, mock_updater):
        """Test that this task runs."""
        start_date = DateHelper().this_month_start.date()
        end_date = DateHelper().today.date()

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

    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    def test_update_summary_tables(self, mock_updater, mock_complete):
        """Test that this task runs."""
        start_date = DateHelper().this_month_start.date()
        end_date = DateHelper().today.date()

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
        start = DateHelper().this_month_start
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
        self.assertIsNotNone(manifest.manifest_completed_datetime)

    def test_mark_manifest_complete_no_manifest(self):
        """Test that we mark a manifest complete."""
        provider = self.ocp_provider
        initial_update_time = provider.data_updated_timestamp
        mark_manifest_complete(
            self.schema, provider.type, manifest_list=None, provider_uuid=str(provider.uuid), tracing_id=1
        )

        provider = Provider.objects.filter(uuid=self.ocp_provider.uuid).first()
        self.assertGreater(provider.data_updated_timestamp, initial_update_time)


@override_settings(HOSTNAME="kokuworker")
class TestWorkerCacheThrottling(MasuTestCase):
    """Tests for tasks that use the worker cache."""

    def single_task_is_running(self, task_name, task_args=None):
        """Check for a single task key in the cache."""
        cache = caches["worker"]
        cache_str = create_single_task_cache_key(task_name, task_args)
        return bool(cache.get(cache_str))

    def lock_single_task(self, task_name, task_args=None, timeout=None):
        """Add a cache entry for a single task to lock a specific task."""
        cache = caches["worker"]
        cache_str = create_single_task_cache_key(task_name, task_args)
        cache.add(cache_str, "kokuworker", 3)

    @patch("masu.processor.tasks.group")
    @patch("masu.processor.tasks.update_summary_tables.s")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_daily_tables")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_update_summary_tables_worker_throttled(
        self,
        mock_inspect,
        mock_lock,
        mock_release,
        mock_update_cost,
        mock_complete,
        mock_chain,
        mock_daily,
        mock_summary,
        mock_delay,
        mock_ocp_on_cloud,
    ):
        """Test that the worker cache is used."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        task_name = "masu.processor.tasks.update_summary_tables"
        start_date = DateHelper().this_month_start
        end_date = DateHelper().this_month_end
        cache_args = [self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, str(start_date.strftime("%Y-%m"))]
        mock_lock.side_effect = self.lock_single_task

        mock_daily.return_value = start_date, end_date
        mock_summary.return_value = start_date, end_date
        update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
        mock_delay.assert_not_called()
        update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
        mock_delay.assert_called()
        self.assertTrue(self.single_task_is_running(task_name, cache_args))
        # Let the cache entry expire
        time.sleep(3)
        self.assertFalse(self.single_task_is_running(task_name, cache_args))

        with patch("masu.processor.tasks.is_large_customer") as mock_customer:
            mock_customer.return_value = True
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
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_daily_tables")
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
        mock_daily,
        mock_summary,
        mock_delay,
    ):
        """Test that the worker cache is used."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        task_name = "masu.processor.tasks.update_summary_tables"
        cache_args = [self.schema]

        start_date = DateHelper().this_month_start
        end_date = DateHelper().this_month_end
        mock_daily.return_value = start_date, end_date
        mock_summary.side_effect = ReportProcessorError
        with self.assertRaises(ReportProcessorError):
            update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
            mock_delay.assert_not_called()
            self.assertFalse(self.single_task_is_running(task_name, cache_args))

    @patch("masu.processor.tasks.update_summary_tables.s")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_daily_tables")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_update_summary_tables_cloud_summary_error(
        self,
        mock_inspect,
        mock_lock,
        mock_release,
        mock_update_cost,
        mock_complete,
        mock_chain,
        mock_daily,
        mock_summary,
        mock_delay,
    ):
        """Test that the update_summary_table cloud exception is caught."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        start_date = DateHelper().this_month_start
        end_date = DateHelper().this_month_end
        mock_daily.return_value = start_date, end_date
        mock_summary.side_effect = ReportSummaryUpdaterCloudError
        expected = "Failed to correlate"
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            update_summary_tables(self.schema, Provider.PROVIDER_AWS, self.aws_provider_uuid, start_date, end_date)
            statement_found = False
            for log in logger.output:
                if expected in log:
                    statement_found = True
            self.assertTrue(statement_found)

    @patch("masu.processor.tasks.update_summary_tables.s")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.tasks.ReportSummaryUpdater.update_daily_tables")
    @patch("masu.processor.tasks.chain")
    @patch("masu.processor.tasks.mark_manifest_complete")
    @patch("masu.processor.tasks.update_cost_model_costs")
    @patch("masu.processor.tasks.WorkerCache.release_single_task")
    @patch("masu.processor.tasks.WorkerCache.lock_single_task")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_update_summary_tables_provider_not_found_error(
        self,
        mock_inspect,
        mock_lock,
        mock_release,
        mock_update_cost,
        mock_complete,
        mock_chain,
        mock_daily,
        mock_summary,
        mock_delay,
    ):
        """Test that the update_summary_table provider not found exception is caught."""
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}
        start_date = DateHelper().this_month_start
        end_date = DateHelper().this_month_end
        mock_daily.return_value = start_date, end_date
        mock_summary.side_effect = ReportSummaryUpdaterProviderNotFoundError
        expected = "Processing for this provier will halt."
        with self.assertLogs("masu.processor.tasks", level="INFO") as logger:
            update_summary_tables(self.schema, Provider.PROVIDER_AWS, str(uuid4()), start_date, end_date)
            statement_found = False
            for log in logger.output:
                if expected in log:
                    statement_found = True
                    break
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

        start_date = DateHelper().last_month_start - relativedelta.relativedelta(months=1)
        end_date = DateHelper().today
        expected_start_date = start_date.strftime("%Y-%m-%d")
        expected_end_date = end_date.strftime("%Y-%m-%d")
        task_name = "masu.processor.tasks.update_cost_model_costs"
        cache_args = [self.schema, self.aws_provider_uuid, expected_start_date, expected_end_date]

        manifest_dict = {
            "assembly_id": "12345",
            "billing_period_start_datetime": DateHelper().today,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
        }

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.add(**manifest_dict)
            manifest.save()

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
        start_date = DateHelper().last_month_start - relativedelta.relativedelta(months=1)
        end_date = DateHelper().today
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
    def test_update_openshift_on_cloud_throttled(self, mock_inspect, mock_lock, mock_release, mock_delay, mock_update):
        """Test that refresh materialized views runs with cache lock."""
        start_date = DateHelper().this_month_start.date()
        end_date = DateHelper().today.date()

        mock_lock.side_effect = self.lock_single_task
        mock_inspect.reserved.return_value = {"celery@kokuworker": []}

        task_name = "masu.processor.tasks.update_openshift_on_cloud"
        cache_args = [self.schema, self.aws_provider_uuid, str(start_date.strftime("%Y-%m"))]

        manifest_dict = {
            "assembly_id": "12345",
            "billing_period_start_datetime": DateHelper().today,
            "num_total_files": 2,
            "provider_uuid": self.aws_provider_uuid,
        }

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.add(**manifest_dict)
            manifest.save()

        update_openshift_on_cloud(
            self.schema,
            self.ocp_on_aws_ocp_provider.uuid,
            self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
        )
        mock_delay.assert_not_called()
        update_openshift_on_cloud(
            self.schema,
            self.ocp_on_aws_ocp_provider.uuid,
            self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            start_date,
            end_date,
        )
        update_openshift_on_cloud(
            self.schema,
            self.ocp_on_aws_ocp_provider.uuid,
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

        with patch("masu.processor.tasks.is_large_customer") as mock_customer:
            mock_customer.return_value = True
            with patch("masu.processor.tasks.rate_limit_tasks") as mock_rate_limit:
                mock_rate_limit.return_value = False
                mock_delay.reset_mock()
                update_openshift_on_cloud(
                    self.schema,
                    self.ocp_on_aws_ocp_provider.uuid,
                    self.aws_provider_uuid,
                    Provider.PROVIDER_AWS,
                    start_date,
                    end_date,
                )
                mock_delay.assert_not_called()

                mock_rate_limit.return_value = True

                update_openshift_on_cloud(
                    self.schema,
                    self.ocp_on_aws_ocp_provider.uuid,
                    self.aws_provider_uuid,
                    Provider.PROVIDER_AWS,
                    start_date,
                    end_date,
                )
                mock_delay.assert_called()


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
            middleware = KokuTenantMiddleware()
            middleware.get_tenant(Tenant, "localhost", mock_request)
            self.assertNotEqual(KokuTenantMiddleware.tenant_cache.currsize, 0)
            remove_stale_tenants()  # Check that it is not clearing the cache unless removing
            self.assertNotEqual(KokuTenantMiddleware.tenant_cache.currsize, 0)
            self.customer.date_updated = DateHelper().n_days_ago(self.customer.date_updated, days)
            self.customer.save()
            before_len = Tenant.objects.count()
            remove_stale_tenants()
            after_len = Tenant.objects.count()
            self.assertGreater(before_len, after_len)
            self.assertEqual(KokuTenantMiddleware.tenant_cache.currsize, 0)
