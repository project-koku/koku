#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportSummaryUpdater object."""
import datetime
from unittest.mock import patch
from uuid import uuid4

from django.test import override_settings

from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.aws.aws_report_parquet_summary_updater import AWSReportParquetSummaryUpdater
from masu.processor.aws.aws_report_summary_updater import AWSReportSummaryUpdater
from masu.processor.azure.azure_report_parquet_summary_updater import AzureReportParquetSummaryUpdater
from masu.processor.azure.azure_report_summary_updater import AzureReportSummaryUpdater
from masu.processor.ocp.ocp_report_summary_updater import OCPReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdaterCloudError
from masu.processor.report_summary_updater import ReportSummaryUpdaterError
from masu.processor.report_summary_updater import ReportSummaryUpdaterProviderNotFoundError
from masu.test import MasuTestCase


class ReportSummaryUpdaterTest(MasuTestCase):
    """Test class for the report summary updater."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        today = DateAccessor().today_with_timezone("UTC")
        cls.today = today.strftime("%Y-%m-%d")
        cls.tomorrow = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        cls.tracing_id = "1234"

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AWSReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AWSReportSummaryUpdater.update_daily_tables")
    def test_aws_route(self, mock_daily, mock_update, mock_cloud):
        """Test that AWS report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)

        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid, tracing_id=self.tracing_id)
        self.assertIsInstance(updater._updater, AWSReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow, self.tracing_id)
        mock_update.assert_called_with(self.today, self.tomorrow)
        mock_cloud.assert_called_with(mock_start, mock_end)

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AWSReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AWSReportSummaryUpdater.update_daily_tables")
    def test_aws_ocp_exception_route(self, mock_daily, mock_update, mock_cloud):
        """Test that AWS report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)
        mock_cloud.side_effect = Exception("test")

        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid, tracing_id=self.tracing_id)
        self.assertIsInstance(updater._updater, AWSReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        with self.assertRaises(ReportSummaryUpdaterCloudError):
            updater.update_summary_tables(self.today, self.tomorrow, self.tracing_id)

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AzureReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AzureReportSummaryUpdater.update_daily_tables")
    def test_azure_route(self, mock_daily, mock_update, mock_cloud):
        """Test that Azure report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)

        updater = ReportSummaryUpdater(self.schema, self.azure_test_provider_uuid, tracing_id=self.tracing_id)
        self.assertIsInstance(updater._updater, AzureReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow, self.tracing_id)
        mock_update.assert_called_with(self.today, self.tomorrow)
        mock_cloud.assert_called_with(mock_start, mock_end)

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AWSReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AWSReportSummaryUpdater.update_daily_tables")
    def test_aws_local_route(self, mock_daily, mock_update, mock_cloud):
        """Test that AWS Local report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)
        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid, tracing_id=self.tracing_id)
        self.assertIsInstance(updater._updater, AWSReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow, self.tracing_id)
        mock_update.assert_called_with(self.today, self.tomorrow)
        mock_cloud.assert_called_with(mock_start, mock_end)

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.OCPReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.OCPReportSummaryUpdater.update_daily_tables")
    def test_ocp_route(self, mock_daily, mock_update, mock_cloud):
        """Test that OCP report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)
        updater = ReportSummaryUpdater(self.schema, self.ocp_test_provider_uuid, tracing_id=self.tracing_id)
        self.assertIsInstance(updater._updater, OCPReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow, self.tracing_id)
        mock_update.assert_called_with(self.today, self.tomorrow)
        mock_cloud.assert_not_called()

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AzureReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AzureReportSummaryUpdater.update_daily_tables")
    def test_azure_local_route(self, mock_daily, mock_update, mock_cloud):
        """Test that AZURE Local report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)
        updater = ReportSummaryUpdater(self.schema, self.azure_test_provider_uuid, tracing_id=self.tracing_id)
        self.assertIsInstance(updater._updater, AzureReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow, self.tracing_id)
        mock_update.assert_called_with(self.today, self.tomorrow)
        mock_cloud.assert_called_with(mock_start, mock_end)

    def test_bad_provider_type(self):
        """Test that an unimplemented provider type throws an error."""
        credentials = {"credentials": {"role_arn": "unknown"}}
        self.unknown_auth = ProviderAuthentication.objects.create(credentials=credentials)
        self.unknown_auth.save()
        data_source = {"data_source": {"bucket": "unknown"}}
        self.unknown_billing_source = ProviderBillingSource.objects.create(data_source=data_source)
        self.unknown_billing_source.save()

        with patch("masu.celery.tasks.check_report_updates"):
            self.unknown_provider = Provider.objects.create(
                uuid=self.unkown_test_provider_uuid,
                name="Test Provider",
                type="FOO",
                authentication=self.unknown_auth,
                billing_source=self.unknown_billing_source,
                customer=self.customer,
                setup_complete=False,
                active=True,
            )
        self.unknown_provider.save()

        with self.assertRaises(ReportSummaryUpdaterError):
            _ = ReportSummaryUpdater(self.schema, self.unkown_test_provider_uuid)

    def test_bad_provider(self):
        """Test that an unknown provider uuid throws an error."""
        with self.assertRaises(ReportSummaryUpdaterProviderNotFoundError):
            _ = ReportSummaryUpdater(self.schema, uuid4())

    def test_no_provider_on_create(self):
        """Test that an error is raised when no provider exists."""
        billing_start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        no_provider_uuid = uuid4()
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_uuid": self.ocp_provider_uuid,
        }
        with ReportManifestDBAccessor() as accessor:
            manifest = accessor.add(**manifest_dict)
        manifest_id = manifest.id
        with self.assertRaises(ReportSummaryUpdaterError):
            ReportSummaryUpdater(self.schema, no_provider_uuid, manifest_id)

    @override_settings(ENABLE_PARQUET_PROCESSING=True)
    def test_aws_parquet_summary_updater(self):
        """Test that the AWSReportParquetSummaryUpdater is returned."""
        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid)

        self.assertIsInstance(updater._updater, AWSReportParquetSummaryUpdater)

    @override_settings(ENABLE_PARQUET_PROCESSING=True)
    def test_azure_parquet_summary_updater(self):
        """Test that the AWSReportParquetSummaryUpdater is returned."""
        updater = ReportSummaryUpdater(self.schema, self.azure_provider_uuid)

        self.assertIsInstance(updater._updater, AzureReportParquetSummaryUpdater)
