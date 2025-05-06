#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportSummaryUpdater object."""
from unittest.mock import patch
from uuid import uuid4

from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from masu.processor.aws.aws_report_parquet_summary_updater import AWSReportParquetSummaryUpdater
from masu.processor.azure.azure_report_parquet_summary_updater import AzureReportParquetSummaryUpdater
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
        cls.tracing_id = "1234"

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

    def test_bad_ocp_provider(self):
        """Test that an OCP provider without cluster-id throws an error."""
        p = self.baker.make("Provider", type="OCP")
        with self.assertRaises(ReportSummaryUpdaterProviderNotFoundError):
            _ = ReportSummaryUpdater(self.schema, p.uuid)

    def test_no_provider_on_create(self):
        """Test that an error is raised when no provider exists."""
        billing_start = self.dh.this_month_start
        no_provider_uuid = uuid4()
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "provider_id": self.ocp_provider_uuid,
        }
        manifest = self.baker.make("CostUsageReportManifest", **manifest_dict)
        manifest_id = manifest.id
        with self.assertRaises(ReportSummaryUpdaterError):
            ReportSummaryUpdater(self.schema, no_provider_uuid, manifest_id)

    def test_aws_parquet_summary_updater(self):
        """Test that the AWSReportParquetSummaryUpdater is returned."""
        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid)

        self.assertIsInstance(updater._updater, AWSReportParquetSummaryUpdater)

    def test_azure_parquet_summary_updater(self):
        """Test that the AzureReportParquetSummaryUpdater is returned."""
        updater = ReportSummaryUpdater(self.schema, self.azure_provider_uuid)
        self.assertIsInstance(updater._updater, AzureReportParquetSummaryUpdater)

    @patch("masu.processor.report_summary_updater.OCPCloudParquetReportSummaryUpdater.update_summary_tables")
    @patch("masu.database.report_manifest_db_accessor.CostUsageReportManifest.objects.select_for_update")
    def test_update_openshift_on_cloud_summary_tables(self, mock_select_for_update, mock_update):
        """Test that we run OCP on Cloud summary."""
        start_date = self.dh.this_month_start
        end_date = self.dh.today
        mock_queryset = mock_select_for_update.return_value
        mock_queryset.get.return_value = None

        updater = ReportSummaryUpdater(self.schema, self.azure_provider_uuid, manifest_id=1)
        updater.update_openshift_on_cloud_summary_tables(
            start_date,
            end_date,
            self.ocp_on_azure_ocp_provider.uuid,
            self.azure_provider_uuid,
            Provider.PROVIDER_AZURE,
            tracing_id=1,
        )
        mock_update.assert_called()

        mock_update.reset_mock()

        # Only run for cloud sources that support OCP on Cloud
        updater = ReportSummaryUpdater(self.schema, self.ocp_on_azure_ocp_provider.uuid)
        updater.update_openshift_on_cloud_summary_tables(
            start_date,
            end_date,
            self.ocp_on_azure_ocp_provider.uuid,
            self.azure_provider_uuid,
            Provider.PROVIDER_AZURE,
            tracing_id=1,
        )
        mock_update.assert_not_called()

        mock_update.reset_mock()

        updater = ReportSummaryUpdater(self.schema, self.azure_provider_uuid, manifest_id=1)
        mock_update.side_effect = Exception
        with self.assertRaises(ReportSummaryUpdaterCloudError):
            updater.update_openshift_on_cloud_summary_tables(
                start_date,
                end_date,
                self.ocp_on_azure_ocp_provider.uuid,
                self.azure_provider_uuid,
                Provider.PROVIDER_AZURE,
                tracing_id=1,
            )
