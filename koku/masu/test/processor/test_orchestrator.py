#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Orchestrator object."""
import logging
import random
from datetime import date
from datetime import datetime
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import faker

from api.models import Provider
from masu.config import Config
from masu.external.report_downloader import ReportDownloaderError
from masu.processor.expired_data_remover import ExpiredDataRemover
from masu.processor.orchestrator import check_currently_processing
from masu.processor.orchestrator import get_billing_month_start
from masu.processor.orchestrator import get_billing_months
from masu.processor.orchestrator import Orchestrator
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn


class FakeDownloader:
    """Fake Downloader for tests."""

    fake = faker.Faker()

    def download_reports(self, number_of_months=1):
        """Create fake downloaded reports."""
        path = "/var/tmp/masu"
        fake_files = []
        for _ in range(1, random.randint(5, 50)):
            fake_files.append(
                {
                    "file": f"{path}/{self.fake.word()}/aws/{self.fake.word()}-{self.fake.word()}.csv",
                    "compression": random.choice(["GZIP", "PLAIN"]),
                }
            )
        return fake_files


class OrchestratorTest(MasuTestCase):
    """Test Cases for the Orchestrator object."""

    fake = faker.Faker()

    def setUp(self):
        """Set up shared variables."""
        super().setUp()
        self.aws_credentials = self.aws_provider.authentication.credentials
        self.aws_data_source = self.aws_provider.billing_source.data_source
        self.azure_credentials = self.azure_provider.authentication.credentials
        self.azure_data_source = self.azure_provider.billing_source.data_source
        self.gcp_credentials = self.gcp_provider.authentication.credentials
        self.gcp_data_source = self.gcp_provider.billing_source.data_source
        self.ocp_credentials = [name[0] for name in Provider.objects.values_list("authentication__credentials")]
        self.ocp_data_source = {}
        self.mock_accounts = [
            {
                "credentials": {"role_arn": fake_arn(service="iam", generate_account_id=True)},
                "data_source": {"bucket": self.fake.word()},
                "customer_name": self.fake.word(),
                "provider_type": Provider.PROVIDER_AWS,
                "schema_name": self.fake.word(),
            },
            {
                "credentials": {},
                "data_source": {},
                "customer_name": self.fake.word(),
                "provider_type": Provider.PROVIDER_GCP,
                "schema_name": self.fake.word(),
            },
        ]

    @patch("masu.processor.orchestrator.update_account_aliases")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.external.report_downloader.ReportDownloader._set_downloader", return_value=FakeDownloader)
    def test_prepare_no_accounts(self, mock_downloader, mock_inspect, mock_account_alias_updater):
        """Test downloading cost usage reports."""
        orchestrator = Orchestrator()
        reports = orchestrator.prepare()

        self.assertIsNone(reports)
        mock_account_alias_updater.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch(
        "masu.processor.orchestrator.is_cloud_source_processing_disabled",
        return_value=True,
    )
    @patch(
        "masu.processor.orchestrator.check_currently_processing",
        return_value=False,
    )
    def test_unleash_is_cloud_source_processing_disabled(self, mock_processing_check, mock_processing, mock_inspect):
        """Test the is_cloud_source_processing_disabled."""
        expected_result = "processing disabled"
        orchestrator = Orchestrator()
        providers = Provider.objects.all()
        for provider in providers:
            provider.polling_timestamp = None
            provider.save()
        with self.assertLogs("masu.processor.orchestrator", level="INFO") as captured_logs:
            orchestrator.get_polling_batch()
            self.assertIn(expected_result, captured_logs.output[0])

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.remove_expired_data.delay", return_value=True)
    def test_remove_expired_report_data(self, mock_task, mock_inspect):
        """Test removing expired report data."""
        orchestrator = Orchestrator()
        results = orchestrator.remove_expired_report_data()
        self.assertTrue(results)
        self.assertEqual(
            len(results), Provider.objects.order_by().distinct("type").count()
        )  # number of distinct provider types

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch.object(ExpiredDataRemover, "remove")
    @patch("masu.processor.orchestrator.remove_expired_data.apply_async", return_value=True)
    def test_remove_expired_report_data_no_accounts(self, mock_task, mock_remover, mock_inspect):
        """Test removing expired report data with no accounts."""
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        mock_remover.return_value = expected_results

        with patch("api.provider.models.Provider.objects", return_value=[]):
            orchestrator = Orchestrator()
            results = orchestrator.remove_expired_report_data()

        self.assertEqual(results, [])

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.update_account_aliases")
    @patch("masu.processor.orchestrator.Orchestrator.start_manifest_processing", side_effect=ReportDownloaderError)
    @patch(
        "masu.processor.orchestrator.check_currently_processing",
        return_value=False,
    )
    def test_prepare_w_downloader_error(
        self, mock_check_processing, mock_task, mock_account_alias_updater, mock_inspect
    ):
        """Test that Orchestrator.prepare() handles downloader errors."""

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_called()
        mock_account_alias_updater.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.update_account_aliases")
    @patch("masu.processor.orchestrator.Orchestrator.start_manifest_processing", side_effect=Exception)
    @patch(
        "masu.processor.orchestrator.check_currently_processing",
        return_value=False,
    )
    def test_prepare_w_exception(self, mock_check_processing, mock_task, mock_account_alias_updater, mock_inspect):
        """Test that Orchestrator.prepare() handles broad exceptions."""

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_called()
        mock_account_alias_updater.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.update_account_aliases")
    @patch("masu.processor.orchestrator.Orchestrator.start_manifest_processing", return_value=([], True))
    @patch(
        "masu.processor.orchestrator.check_currently_processing",
        return_value=False,
    )
    def test_prepare_w_manifest_processing_successful(
        self, mock_check_processing, mock_task, mock_account_alias_updater, mock_inspect
    ):
        """Test that Orchestrator.prepare() works when manifest processing is successful."""
        # mock_account_alias_updater().get_label_details.return_value = (True, True)

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_account_alias_updater.assert_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.update_account_aliases")
    @patch("masu.processor.orchestrator.Orchestrator.start_manifest_processing", return_value=([], True))
    @patch(
        "masu.processor.orchestrator.check_currently_processing",
        return_value=False,
    )
    def test_prepare_w_ingress_reports_processing_successful(
        self, mock_check_processing, mock_task, mock_account_alias_updater, mock_inspect
    ):
        """Test that Orchestrator.prepare() works when manifest processing is successful."""
        # mock_account_alias_updater().get_label_details.return_value = (True, True)
        ingress_reports = ["test"]

        orchestrator = Orchestrator(ingress_reports=ingress_reports, bill_date="202302")
        orchestrator.prepare()
        mock_account_alias_updater.assert_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.update_account_aliases")
    @patch("masu.processor.orchestrator.get_report_files.apply_async", return_value=True)
    def test_prepare_w_no_manifest_found(self, mock_task, mock_account_alias_updater, mock_inspect):
        """Test that Orchestrator.prepare() is skipped when no manifest is found."""
        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_not_called()
        mock_account_alias_updater.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.record_report_status", return_value=True)
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_start_manifest_processing_already_progressed(
        self, mock_download_manifest, mock_chord, mock_task, mock_inspect
    ):
        """Test start_manifest_processing with report already processed."""
        mock_manifests = [{"manifest_id": "1", "files": [{"local_file": {}}]}]
        mock_download_manifest.return_value = mock_manifests
        orchestrator = Orchestrator()
        account = self.mock_accounts[0]

        orchestrator.start_manifest_processing(
            account.get("customer_name"),
            account.get("credentials"),
            account.get("data_source"),
            "AWS-local",
            account.get("schema_name"),
            account.get("provider_uuid"),
            get_billing_months(1)[0],
        )
        mock_chord.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.record_report_status", return_value=False)
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_start_manifest_processing_record_report_status_return_false(
        self, mock_download, mock_chord, mock_task, mock_inspect
    ):
        """Test start_manifest_processing with report already processed."""
        mock_manifests = [
            {
                "manifest_id": "1",
                "files": [{"local_file": {}}],
                "assembly_id": "1234",
            }
        ]
        mock_download.return_value = mock_manifests
        orchestrator = Orchestrator()
        account = self.mock_accounts[0]

        orchestrator.start_manifest_processing(
            account.get("customer_name"),
            account.get("credentials"),
            account.get("data_source"),
            "AWS-local",
            account.get("schema_name"),
            account.get("provider_uuid"),
            get_billing_months(1)[0],
        )
        mock_chord.assert_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.record_report_status", return_value=False)
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_start_manifest_processing_with_large_provider(self, mock_download, mock_chord, mock_task, mock_inspect):
        """Test setting provider as large based on report file count."""
        fake_files = []
        for _ in range(101):
            fake_files.append({"local_file": f"{faker.Faker().word()}.csv"})
        mock_manifests = [
            {
                "manifest_id": "1",
                "files": fake_files,
                "assembly_id": "1234",
            }
        ]
        mock_download.return_value = mock_manifests
        orchestrator = Orchestrator()
        account = self.mock_accounts[0]
        expected = "marking provider large as report files exceed threshold."
        with self.assertLogs("masu.processor.orchestrator", level="INFO") as logger:
            orchestrator.start_manifest_processing(
                account.get("customer_name"),
                account.get("credentials"),
                account.get("data_source"),
                "AWS-local",
                account.get("schema_name"),
                account.get("provider_uuid"),
                get_billing_months(1)[0],
            )
            mock_chord.assert_called()
            self.assertTrue(any(expected in log for log in logger.output))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.WorkerCache.task_is_running", return_value=True)
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_start_manifest_processing_in_progress(self, mock_download, mock_chord, mock_worker_cache, mock_inspect):
        """Test start_manifest_processing with report in progressed."""
        mock_manifests = [{"manifest_id": "1", "files": [{"local_file": {}}]}]
        mock_download.return_value = mock_manifests
        orchestrator = Orchestrator()
        account = self.mock_accounts[0]

        orchestrator.start_manifest_processing(
            account.get("customer_name"),
            account.get("credentials"),
            account.get("data_source"),
            "AWS-local",
            account.get("schema_name"),
            account.get("provider_uuid"),
            get_billing_months(1)[0],
        )
        mock_chord.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_start_manifest_processing(self, mock_download_manifest, mock_task, mock_inspect):
        """Test start_manifest_processing."""
        test_matrix = [
            {"mock_downloader_manifest_list": [], "expect_chord_called": False},
            {
                "mock_downloader_manifest_list": [
                    {
                        "manifest_id": 1,
                        "files": [{"local_file": "file1.csv", "key": "filekey"}],
                    }
                ],
                "expect_chord_called": True,
            },
        ]
        for test in test_matrix:
            mock_download_manifest.return_value = test.get("mock_downloader_manifest_list")
            orchestrator = Orchestrator()
            account = self.mock_accounts[0]
            orchestrator.start_manifest_processing(
                account.get("customer_name"),
                account.get("credentials"),
                account.get("data_source"),
                "AWS-local",
                account.get("schema_name"),
                account.get("provider_uuid"),
                get_billing_months(1)[0],
            )
            if test.get("expect_chord_called"):
                mock_task.assert_called()
            else:
                mock_task.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.group")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_start_manifest_processing_priority_queue(
        self, mock_download_manifest, mock_task, mock_group, mock_inspect
    ):
        """Test start_manifest_processing using priority queue."""
        test_queues = [
            {
                "name": "qe-account",
                "provider_uuid": str(uuid4()),
                "queue-name": "priority",
                "summary-expected": "priority",
                "hcs-expected": "priority",
            },
            {
                "name": "qe-account",
                "provider_uuid": None,
                "queue-name": "priority",
                "summary-expected": "summary",
                "hcs-expected": "hcs",
            },
            {
                "name": "qe-account",
                "provider_uuid": str(uuid4()),
                "queue-name": None,
                "summary-expected": "summary",
                "hcs-expected": "hcs",
            },
            {
                "name": "qe-account",
                "provider_uuid": None,
                "queue-name": None,
                "summary-expected": "summary",
                "hcs-expected": "hcs",
            },
        ]
        mock_manifest = {
            "mock_downloader_manifest_list": [
                {"manifest_id": 1, "files": [{"local_file": "file1.csv", "key": "filekey"}]}
            ]
        }
        for test in test_queues:
            with self.subTest(test=test.get("name")):
                mock_download_manifest.return_value = mock_manifest.get("mock_downloader_manifest_list")
                orchestrator = Orchestrator(provider_uuid=test.get("provider_uuid"), queue_name=test.get("queue-name"))
                account = self.mock_accounts[0]
                orchestrator.start_manifest_processing(
                    account.get("customer_name"),
                    account.get("credentials"),
                    account.get("data_source"),
                    "AWS-local",
                    account.get("schema_name"),
                    account.get("provider_uuid"),
                    get_billing_months(1)[0],
                )
                summary_actual_queue = mock_task.call_args.args[0].options.get("queue")
                hcs_actual_queue = mock_task.call_args.args[1].options.get("queue")

                self.assertEqual(summary_actual_queue, test.get("summary-expected"))
                self.assertEqual(hcs_actual_queue, test.get("hcs-expected"))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.group")
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_start_manifest_processing_no_resummary(
        self, mock_download_manifest, mock_chord, mock_group, mock_inspect
    ):
        """Test start_manifest_processing."""
        test_matrix = [
            {"mock_downloader_manifest_list": [], "expect_chord_called": False, "expected_chain_called": False},
            {
                "mock_downloader_manifest_list": [
                    {
                        "manifest_id": 1,
                        "files": [{"local_file": "file1.csv", "key": "filekey"}],
                    }
                ],
                "expect_chord_called": False,
                "expected_chain_called": True,
            },
        ]
        for test in test_matrix:
            mock_download_manifest.return_value = test.get("mock_downloader_manifest_list")
            orchestrator = Orchestrator(summarize_reports=False)
            account = self.mock_accounts[0]
            orchestrator.start_manifest_processing(
                account.get("customer_name"),
                account.get("credentials"),
                account.get("data_source"),
                "AWS-local",
                account.get("schema_name"),
                account.get("provider_uuid"),
                get_billing_months(1)[0],
            )
            if test.get("expect_chord_called"):
                mock_chord.assert_called()
            else:
                mock_chord.assert_not_called()
            if test.get("expected_chain_called"):
                mock_group.assert_called()
            else:
                mock_group.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.check_provider_setup_complete")
    def test_get_reports(self, mock_check_setup_complete, mock_inspect):
        """Test get_reports for combinations of setup_complete and ingest override."""
        initial_month_qty = Config.INITIAL_INGEST_NUM_MONTHS
        test_matrix = [
            {"get_setup_complete": True, "ingest_override": True, "test_months": 5, "expected_month_length": 5},
            {"get_setup_complete": False, "ingest_override": True, "test_months": 5, "expected_month_length": 5},
            {"get_setup_complete": True, "ingest_override": False, "test_months": 5, "expected_month_length": 2},
            {"get_setup_complete": False, "ingest_override": False, "test_months": 5, "expected_month_length": 5},
        ]
        for test in test_matrix:
            test_months = test.get("test_months")
            mock_check_setup_complete.return_value = test.get("get_setup_complete")
            Config.INGEST_OVERRIDE = test.get("ingest_override")
            Config.INITIAL_INGEST_NUM_MONTHS = test_months

            orchestrator = Orchestrator()
            months = orchestrator.get_reports(self.aws_provider_uuid)
            self.assertEqual(test.get("expected_month_length"), len(months))
            for i in range(1, len(months)):
                self.assertLess(months[i], months[i - 1])

        Config.INGEST_OVERRIDE = False
        Config.INITIAL_INGEST_NUM_MONTHS = initial_month_qty

        expected = [self.dh.this_month_start.date()]
        orchestrator = Orchestrator(bill_date=self.dh.today)
        result = orchestrator.get_reports(self.aws_provider_uuid)
        self.assertEqual(result, expected)

    @patch("masu.processor.orchestrator.WorkerCache")
    def test_orchestrator_args_polling_batch(self, *args):
        """Test that args to Orchestrator change the polling-batch result"""
        # providing a UUID overrides the polling timestamp
        o = Orchestrator(provider_uuid=self.aws_provider_uuid)
        p = o.get_polling_batch()
        self.assertEqual(len(p), 1)

        # provider provider-type does NOT override polling timestamp
        # so this query will provide zero pollable providers
        o = Orchestrator(provider_type="AWS-local")
        p = o.get_polling_batch()
        self.assertEqual(len(p), 0)

        # here we demonstrate the filtering only returns AWS-local
        # and returns based on the polling timestamp
        expected_providers = Provider.objects.filter(type=Provider.PROVIDER_AWS_LOCAL)
        p = expected_providers[0]
        p.polling_timestamp = None
        p.save()

        o = Orchestrator(provider_type="AWS-local")
        p = o.get_polling_batch()
        self.assertGreater(len(p), 0)
        self.assertEqual(len(p), expected_providers.count())

        # Check polling time updated while we are still processing
        with patch("masu.processor.orchestrator.check_currently_processing", return_value=True):
            o = Orchestrator(type=Provider.PROVIDER_AWS_LOCAL)
            p = o.get_polling_batch()
            self.assertEqual(len(p), 0)

    def test_get_billing_months(self):
        """Test get_billing_months"""
        # test that num_months = 1 returns the current month
        result = get_billing_months(1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result, [self.dh.this_month_start.date()])

        # test that num_months = 2 returns 2 months and assert the order is latest month first
        result = get_billing_months(2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result, [self.dh.this_month_start.date(), self.dh.last_month_start.date()])

        # test that num_month = 5 returns 5 unique entires and that the first index is the current month
        result = get_billing_months(5)
        self.assertEqual(len(set(result)), 5)
        self.assertEqual(result[0], self.dh.this_month_start.date())

    def test_get_billing_month_start(self):
        """Test get_billing_month_start returns the first of the month in the date provided."""
        today = self.dh.today
        result = get_billing_month_start(str(today))
        self.assertEqual(result, self.dh.this_month_start.date())

        result = get_billing_month_start(today)
        self.assertEqual(result, self.dh.this_month_start.date())

        result = get_billing_month_start(today.date())
        self.assertEqual(result, self.dh.this_month_start.date())

        test_input = datetime(year=2020, month=6, day=25)
        expected = date(year=2020, month=6, day=1)
        result = get_billing_month_start("20200625")
        self.assertEqual(result, expected)
        result = get_billing_month_start("2020-06-25")
        self.assertEqual(result, expected)
        result = get_billing_month_start("2020-6-25")
        self.assertEqual(result, expected)

        result = get_billing_month_start(test_input)
        self.assertEqual(result, expected)

        result = get_billing_month_start(test_input.date())
        self.assertEqual(result, expected)

    def test_check_currently_processing(self):
        """Test to check if we should poll a provider that may have tasks in progress."""
        now = self.dh.now_utc
        # Check we would process if not processed before
        result = check_currently_processing(self.schema_name, self.ocp_provider)
        self.assertEqual(result, False)
        # Check we have task processing, no polling
        one_days_ago = now - timedelta(days=1)
        two_days_ago = now - timedelta(days=2)
        provider_processing = SimpleNamespace()
        provider_processing.polling_timestamp = one_days_ago
        provider_processing.data_updated_timestamp = two_days_ago
        result = check_currently_processing(self.schema_name, provider_processing)
        self.assertEqual(result, True)
        # Check we have task processing but likely failed, needs repolling
        seven_days_ago = now - timedelta(days=7)
        provider_failed = SimpleNamespace()
        provider_failed.polling_timestamp = two_days_ago
        provider_failed.data_updated_timestamp = seven_days_ago
        result = check_currently_processing(self.schema_name, provider_failed)
        self.assertEqual(result, False)
        # Check we have task processing but likely failed, needs repolling
        with patch("masu.processor.orchestrator.is_customer_large", return_value=True):
            nine_days_ago = now - timedelta(days=9)
            provider_failed = SimpleNamespace()
            provider_failed.polling_timestamp = two_days_ago
            provider_failed.data_updated_timestamp = nine_days_ago
            result = check_currently_processing(self.schema_name, provider_failed)
            self.assertEqual(result, False)
        # Check initial ingest
        initial_prov = SimpleNamespace()
        initial_prov.polling_timestamp = now
        initial_prov.created_timestamp = now
        initial_prov.data_updated_timestamp = None
        result = check_currently_processing(self.schema_name, initial_prov)
        self.assertEqual(result, False)
        # Check initial ingest processing
        provider_initial_prov = SimpleNamespace()
        provider_initial_prov.polling_timestamp = now
        provider_initial_prov.created_timestamp = one_days_ago
        provider_initial_prov.data_updated_timestamp = None
        result = check_currently_processing(self.schema_name, provider_initial_prov)
        self.assertEqual(result, True)
        # Check initial ingest failed, needs repolling
        initial_prov_failed = SimpleNamespace()
        initial_prov_failed.polling_timestamp = now
        initial_prov_failed.created_timestamp = nine_days_ago
        initial_prov_failed.data_updated_timestamp = None
        result = check_currently_processing(self.schema_name, initial_prov_failed)
        self.assertEqual(result, False)

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch.object(ExpiredDataRemover, "remove_expired_trino_partitions")
    @patch("masu.processor.orchestrator.remove_expired_trino_partitions.delay")
    def test_remove_expired_trino_partitions(self, mock_task, mock_remover, mock_inspect):
        """Test removing expired trino partitions."""
        task_id = "123"
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        mock_remover.return_value = expected_results
        mock_task.return_value = task_id
        expected = (
            "INFO:masu.processor.orchestrator:Expired partition removal queued - schema_name: org1234567, Task ID: {}"
        )
        # unset disabling all logging below CRITICAL from masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs("masu.processor.orchestrator", level="INFO") as logger:
            orchestrator = Orchestrator()
            results = orchestrator.remove_expired_trino_partitions()
            self.assertTrue(results)
            self.assertEqual(len(results), 1)
            self.assertIn(expected.format(task_id), logger.output)
