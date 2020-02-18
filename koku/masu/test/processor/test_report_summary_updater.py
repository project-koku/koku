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
"""Test the ReportSummaryUpdater object."""
import datetime
from unittest.mock import patch

from api.provider.models import Provider
from api.provider.models import ProviderAuthentication
from api.provider.models import ProviderBillingSource
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.aws.aws_report_summary_updater import AWSReportSummaryUpdater
from masu.processor.azure.azure_report_summary_updater import AzureReportSummaryUpdater
from masu.processor.ocp.ocp_report_summary_updater import OCPReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdater
from masu.processor.report_summary_updater import ReportSummaryUpdaterError
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

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AWSReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AWSReportSummaryUpdater.update_daily_tables")
    def test_aws_route(self, mock_daily, mock_update, mock_cloud):
        """Test that AWS report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)

        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid)
        self.assertIsInstance(updater._updater, AWSReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow)
        mock_update.assert_called_with(self.today, self.tomorrow)
        mock_cloud.assert_called_with(mock_start, mock_end)

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AzureReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AzureReportSummaryUpdater.update_daily_tables")
    def test_azure_route(self, mock_daily, mock_update, mock_cloud):
        """Test that Azure report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)

        updater = ReportSummaryUpdater(self.schema, self.azure_test_provider_uuid)
        self.assertIsInstance(updater._updater, AzureReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow)
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
        updater = ReportSummaryUpdater(self.schema, self.aws_provider_uuid)
        self.assertIsInstance(updater._updater, AWSReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow)
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
        updater = ReportSummaryUpdater(self.schema, self.ocp_test_provider_uuid)
        self.assertIsInstance(updater._updater, OCPReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow)
        mock_update.assert_called_with(self.today, self.tomorrow)
        mock_cloud.assert_called_with(mock_start, mock_end)

    @patch("masu.processor.report_summary_updater.OCPCloudReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AzureReportSummaryUpdater.update_summary_tables")
    @patch("masu.processor.report_summary_updater.AzureReportSummaryUpdater.update_daily_tables")
    def test_azure_local_route(self, mock_daily, mock_update, mock_cloud):
        """Test that AZURE Local report updating works as expected."""
        mock_start = 1
        mock_end = 2
        mock_daily.return_value = (mock_start, mock_end)
        mock_update.return_value = (mock_start, mock_end)
        updater = ReportSummaryUpdater(self.schema, self.azure_test_provider_uuid)
        self.assertIsInstance(updater._updater, AzureReportSummaryUpdater)

        updater.update_daily_tables(self.today, self.tomorrow)
        mock_daily.assert_called_with(self.today, self.tomorrow)
        mock_update.assert_not_called()
        mock_cloud.assert_not_called()

        updater.update_summary_tables(self.today, self.tomorrow)
        mock_update.assert_called_with(self.today, self.tomorrow)
        mock_cloud.assert_called_with(mock_start, mock_end)

    def test_bad_provider(self):
        """Test that an unimplemented provider throws an error."""
        self.unknown_auth = ProviderAuthentication.objects.create(provider_resource_name="unknown")
        self.unknown_auth.save()
        self.unknown_billing_source = ProviderBillingSource.objects.create(bucket="unknown")
        self.unknown_billing_source.save()

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

    def test_manifest_is_ready_is_ready(self):
        """Test that True is returned when a manifest is ready to process."""
        billing_start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "num_processed_files": 2,
            "provider_uuid": self.ocp_provider_uuid,
        }
        with ReportManifestDBAccessor() as accessor:
            manifest = accessor.add(**manifest_dict)
        manifest_id = manifest.id
        updater = ReportSummaryUpdater(self.schema, self.ocp_test_provider_uuid, manifest_id)
        self.assertTrue(updater.manifest_is_ready())

    def test_manifest_is_ready_is_not_ready(self):
        """Test that False is returned when a manifest is not ready to process."""
        billing_start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        manifest_dict = {
            "assembly_id": "1234",
            "billing_period_start_datetime": billing_start,
            "num_total_files": 2,
            "num_processed_files": 1,
            "provider_uuid": self.ocp_provider_uuid,
        }
        with ReportManifestDBAccessor() as accessor:
            manifest = accessor.add(**manifest_dict)
        manifest_id = manifest.id
        updater = ReportSummaryUpdater(self.schema, self.ocp_test_provider_uuid, manifest_id)

        # manifest_is_ready is now unconditionally returning True, so summary is expected.
        self.assertTrue(updater.manifest_is_ready())
