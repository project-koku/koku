#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Orchestrator object."""
import logging
import random
from unittest.mock import patch

import faker

from api.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.external.accounts_accessor import AccountsAccessor
from masu.external.accounts_accessor import AccountsAccessorError
from masu.external.date_accessor import DateAccessor
from masu.external.report_downloader import ReportDownloaderError
from masu.processor.expired_data_remover import ExpiredDataRemover
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
                    "file": "{}/{}/aws/{}-{}.csv".format(path, self.fake.word(), self.fake.word(), self.fake.word()),
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
            }
        ]

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    def test_initializer(self, mock_inspect):  # noqa: C901
        """Test to init."""
        orchestrator = Orchestrator()
        provider_count = Provider.objects.filter(active=True).count()
        if len(orchestrator._accounts) != provider_count:
            self.fail("Unexpected number of test accounts")

        for account in orchestrator._accounts:
            with self.subTest(provider_type=account.get("provider_type")):
                if account.get("provider_type") in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
                    self.assertEqual(account.get("credentials"), self.aws_credentials)
                    self.assertEqual(account.get("data_source"), self.aws_data_source)
                    self.assertEqual(account.get("customer_name"), self.schema)
                elif account.get("provider_type") == Provider.PROVIDER_OCP:
                    self.assertIn(account.get("credentials"), self.ocp_credentials)
                    self.assertEqual(account.get("data_source"), self.ocp_data_source)
                    self.assertEqual(account.get("customer_name"), self.schema)
                elif account.get("provider_type") in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
                    self.assertEqual(account.get("credentials"), self.azure_credentials)
                    self.assertEqual(account.get("data_source"), self.azure_data_source)
                    self.assertEqual(account.get("customer_name"), self.schema)
                elif account.get("provider_type") in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
                    self.assertEqual(account.get("credentials"), self.gcp_credentials)
                    self.assertEqual(account.get("data_source"), self.gcp_data_source)
                    self.assertEqual(account.get("customer_name"), self.schema)
                else:
                    self.fail("Unexpected provider")

        if len(orchestrator._polling_accounts) != 3:
            self.fail("Unexpected number of listener test accounts")

        for account in orchestrator._polling_accounts:
            with self.subTest(provider_type=account.get("provider_type")):
                if account.get("provider_type") in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
                    self.assertEqual(account.get("credentials"), self.aws_credentials)
                    self.assertEqual(account.get("data_source"), self.aws_data_source)
                    self.assertEqual(account.get("customer_name"), self.schema)
                elif account.get("provider_type") in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
                    self.assertEqual(account.get("credentials"), self.azure_credentials)
                    self.assertEqual(account.get("data_source"), self.azure_data_source)
                    self.assertEqual(account.get("customer_name"), self.schema)
                elif account.get("provider_type") in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
                    self.assertEqual(account.get("credentials"), self.gcp_credentials)
                    self.assertEqual(account.get("data_source"), self.gcp_data_source)
                    self.assertEqual(account.get("customer_name"), self.schema)
                else:
                    self.fail("Unexpected provider")

    @patch("masu.processor.orchestrator.AccountLabel")
    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.external.report_downloader.ReportDownloader._set_downloader", return_value=FakeDownloader)
    @patch("masu.external.accounts_accessor.AccountsAccessor.get_accounts", return_value=[])
    def test_prepare_no_accounts(self, mock_downloader, mock_accounts_accessor, mock_inspect, mock_account_labler):
        """Test downloading cost usage reports."""
        orchestrator = Orchestrator()
        reports = orchestrator.prepare()

        self.assertIsNone(reports)
        mock_account_labler.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch.object(AccountsAccessor, "get_accounts")
    def test_init_all_accounts(self, mock_accessor, mock_inspect):
        """Test initializing orchestrator with forced billing source."""
        mock_accessor.return_value = self.mock_accounts
        orchestrator_all = Orchestrator()
        self.assertEqual(orchestrator_all._accounts, self.mock_accounts)

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch.object(AccountsAccessor, "get_accounts")
    def test_init_with_billing_source(self, mock_accessor, mock_inspect):
        """Test initializing orchestrator with forced billing source."""
        mock_accessor.return_value = self.mock_accounts

        fake_source = random.choice(self.mock_accounts)

        individual = Orchestrator(fake_source.get("data_source"))
        self.assertEqual(len(individual._accounts), 1)
        found_account = individual._accounts[0]
        self.assertEqual(found_account.get("data_source"), fake_source.get("data_source"))

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch.object(AccountsAccessor, "get_accounts")
    def test_init_all_accounts_error(self, mock_accessor, mock_inspect):
        """Test initializing orchestrator accounts error."""
        mock_accessor.side_effect = AccountsAccessorError("Sample timeout error")
        try:
            Orchestrator()
        except Exception:
            self.fail("unexpected error")

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch.object(ExpiredDataRemover, "remove")
    @patch("masu.processor.orchestrator.remove_expired_data.apply_async", return_value=True)
    def test_remove_expired_report_data(self, mock_task, mock_remover, mock_inspect):
        """Test removing expired report data."""
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        mock_remover.return_value = expected_results

        expected = "INFO:masu.processor.orchestrator:Expired data removal queued - schema_name: acct10001, Task ID: {}"
        # unset disabling all logging below CRITICAL from masu/__init__.py
        logging.disable(logging.NOTSET)
        with self.assertLogs("masu.processor.orchestrator", level="INFO") as logger:
            orchestrator = Orchestrator()
            results = orchestrator.remove_expired_report_data()
            self.assertTrue(results)
            self.assertEqual(len(results), 5)
            async_id = results.pop().get("async_id")
            self.assertIn(expected.format(async_id), logger.output)

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch.object(AccountsAccessor, "get_accounts")
    @patch.object(ExpiredDataRemover, "remove")
    @patch("masu.processor.orchestrator.remove_expired_data.apply_async", return_value=True)
    def test_remove_expired_report_data_no_accounts(self, mock_task, mock_remover, mock_accessor, mock_inspect):
        """Test removing expired report data with no accounts."""
        expected_results = [{"account_payer_id": "999999999", "billing_period_start": "2018-06-24 15:47:33.052509"}]
        mock_remover.return_value = expected_results
        mock_accessor.return_value = []

        orchestrator = Orchestrator()
        results = orchestrator.remove_expired_report_data()

        self.assertEqual(results, [])

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.AccountLabel", spec=True)
    @patch("masu.processor.orchestrator.Orchestrator.start_manifest_processing", side_effect=ReportDownloaderError)
    def test_prepare_w_downloader_error(self, mock_task, mock_labeler, mock_inspect):
        """Test that Orchestrator.prepare() handles downloader errors."""

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_called()
        mock_labeler.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.AccountLabel", spec=True)
    @patch("masu.processor.orchestrator.Orchestrator.start_manifest_processing", side_effect=Exception)
    def test_prepare_w_exception(self, mock_task, mock_labeler, mock_inspect):
        """Test that Orchestrator.prepare() handles broad exceptions."""

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_called()
        mock_labeler.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.AccountLabel", spec=True)
    @patch("masu.processor.orchestrator.Orchestrator.start_manifest_processing", return_value=([], True))
    def test_prepare_w_manifest_processing_successful(self, mock_task, mock_labeler, mock_inspect):
        """Test that Orchestrator.prepare() works when manifest processing is successful."""
        mock_labeler().get_label_details.return_value = (True, True)

        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_labeler.assert_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.AccountLabel", spec=True)
    @patch("masu.processor.orchestrator.get_report_files.apply_async", return_value=True)
    def test_prepare_w_no_manifest_found(self, mock_task, mock_labeler, mock_inspect):
        """Test that Orchestrator.prepare() is skipped when no manifest is found."""
        orchestrator = Orchestrator()
        orchestrator.prepare()
        mock_task.assert_not_called()
        mock_labeler.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.record_report_status", return_value=True)
    @patch("masu.processor.orchestrator.chord", return_value=True)
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest", return_value={})
    def test_start_manifest_processing_already_progressed(
        self, mock_record_report_status, mock_download_manifest, mock_task, mock_inspect
    ):
        """Test start_manifest_processing with report already processed."""
        orchestrator = Orchestrator()
        account = self.mock_accounts[0]

        orchestrator.start_manifest_processing(
            account.get("customer_name"),
            account.get("credentials"),
            account.get("data_source"),
            "AWS-local",
            account.get("schema_name"),
            account.get("provider_uuid"),
            DateAccessor().get_billing_months(1)[0],
        )
        mock_task.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.WorkerCache.task_is_running", return_value=True)
    @patch("masu.processor.orchestrator.chord", return_value=True)
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest", return_value={})
    def test_start_manifest_processing_in_progress(
        self, mock_record_report_status, mock_download_manifest, mock_task, mock_inspect
    ):
        """Test start_manifest_processing with report in progressed."""
        orchestrator = Orchestrator()
        account = self.mock_accounts[0]

        orchestrator.start_manifest_processing(
            account.get("customer_name"),
            account.get("credentials"),
            account.get("data_source"),
            "AWS-local",
            account.get("schema_name"),
            account.get("provider_uuid"),
            DateAccessor().get_billing_months(1)[0],
        )
        mock_task.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.processor.orchestrator.chord")
    @patch("masu.processor.orchestrator.ReportDownloader.download_manifest")
    def test_start_manifest_processing(self, mock_download_manifest, mock_task, mock_inspect):
        """Test start_manifest_processing."""
        test_matrix = [
            {"mock_downloader_manifest": {}, "expect_chord_called": False},
            {
                "mock_downloader_manifest": {
                    "manifest_id": 1,
                    "files": [{"local_file": "file1.csv", "key": "filekey"}],
                },
                "expect_chord_called": True,
            },
        ]
        for test in test_matrix:
            mock_download_manifest.return_value = test.get("mock_downloader_manifest")
            orchestrator = Orchestrator()
            account = self.mock_accounts[0]
            orchestrator.start_manifest_processing(
                account.get("customer_name"),
                account.get("credentials"),
                account.get("data_source"),
                "AWS-local",
                account.get("schema_name"),
                account.get("provider_uuid"),
                DateAccessor().get_billing_months(1)[0],
            )
            if test.get("expect_chord_called"):
                mock_task.assert_called()
            else:
                mock_task.assert_not_called()

    @patch("masu.processor.worker_cache.CELERY_INSPECT")
    @patch("masu.database.provider_db_accessor.ProviderDBAccessor.get_setup_complete")
    def test_get_reports(self, fake_accessor, mock_inspect):
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
            fake_accessor.return_value = test.get("get_setup_complete")
            Config.INGEST_OVERRIDE = test.get("ingest_override")
            Config.INITIAL_INGEST_NUM_MONTHS = test_months

            orchestrator = Orchestrator()
            months = orchestrator.get_reports(self.aws_provider_uuid)
            self.assertEqual(test.get("expected_month_length"), len(months))
            for i in range(1, len(months)):
                self.assertLess(months[i], months[i - 1])

        Config.INGEST_OVERRIDE = False
        Config.INITIAL_INGEST_NUM_MONTHS = initial_month_qty

        dh = DateHelper()
        expected = [dh.this_month_start.date()]
        orchestrator = Orchestrator(bill_date=dh.today)
        result = orchestrator.get_reports(self.aws_provider_uuid)
        self.assertEqual(result, expected)
