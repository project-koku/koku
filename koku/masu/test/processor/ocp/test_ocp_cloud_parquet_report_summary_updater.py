#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPCloudParquetReportSummaryUpdaterTest."""
import datetime
import decimal
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from tenant_schemas.utils import schema_context

from api.models import Provider
from api.utils import DateHelper
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.test import MasuTestCase


class OCPCloudParquetReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPCloudParquetReportSummaryUpdaterTest class."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.dh = DateHelper()

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.today = self.dh.today

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_tags_summary_table"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary_presto"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.aws_get_bills_from_provider")
    def test_update_aws_summary_tables(self, mock_utility, mock_ocp_on_aws, mock_tag_summary, mock_map):
        """Test that summary tables are properly run for an OCP provider."""
        fake_bills = MagicMock()
        fake_bills.__iter__.return_value = [Mock(), Mock()]
        first = Mock()
        bill_id = 1
        first.return_value.id = bill_id
        fake_bills.first = first
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with ProviderDBAccessor(self.aws_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with OCPReportDBAccessor(self.schema_name) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(self.ocp_test_provider_uuid, start_date)
        with schema_context(self.schema_name):
            current_ocp_report_period_id = report_period.id

        mock_map.return_value = {self.ocp_test_provider_uuid: (self.aws_provider_uuid, Provider.PROVIDER_AWS)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="acct10001", provider=provider, manifest=None)
        updater.update_aws_summary_tables(
            self.ocp_test_provider_uuid, self.aws_test_provider_uuid, start_date, end_date
        )
        mock_ocp_on_aws.assert_called_with(
            start_date,
            end_date,
            self.ocp_test_provider_uuid,
            self.aws_test_provider_uuid,
            current_ocp_report_period_id,
            bill_id,
            decimal.Decimal(0),
        )

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_tags_summary_table"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_cost_daily_summary_presto"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.azure_get_bills_from_provider")
    def test_update_azure_summary_tables(self, mock_utility, mock_ocp_on_azure, mock_tag_summary, mock_map):
        """Test that summary tables are properly run for an OCP provider."""
        fake_bills = MagicMock()
        fake_bills.__iter__.return_value = [Mock(), Mock()]
        first = Mock()
        bill_id = 1
        first.return_value.id = bill_id
        fake_bills.first = first
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with ProviderDBAccessor(self.azure_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with ProviderDBAccessor(self.ocp_test_provider_uuid) as provider_accessor:
            credentials = provider_accessor.get_credentials()
        cluster_id = credentials.get("cluster_id")
        mock_map.return_value = {self.ocp_test_provider_uuid: (self.azure_provider_uuid, Provider.PROVIDER_AZURE)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="acct10001", provider=provider, manifest=None)
        updater.update_azure_summary_tables(
            self.ocp_test_provider_uuid, self.azure_test_provider_uuid, start_date, end_date
        )
        mock_ocp_on_azure.assert_called_with(
            start_date,
            end_date,
            self.ocp_test_provider_uuid,
            self.azure_test_provider_uuid,
            cluster_id,
            bill_id,
            decimal.Decimal(0),
        )

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_tags_summary_table"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_cost_daily_summary_presto"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.azure_get_bills_from_provider")
    def test_update_azure_summary_tables_with_string_dates(
        self, mock_utility, mock_ocp_on_azure, mock_tag_summary, mock_map
    ):
        """Test that summary tables are properly run for an OCP provider."""
        fake_bills = MagicMock()
        fake_bills.__iter__.return_value = [Mock(), Mock()]
        first = Mock()
        bill_id = 1
        first.return_value.id = bill_id
        fake_bills.first = first
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with ProviderDBAccessor(self.azure_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with ProviderDBAccessor(self.ocp_test_provider_uuid) as provider_accessor:
            credentials = provider_accessor.get_credentials()
        cluster_id = credentials.get("cluster_id")
        mock_map.return_value = {self.ocp_test_provider_uuid: (self.azure_provider_uuid, Provider.PROVIDER_AZURE)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="acct10001", provider=provider, manifest=None)
        updater.update_azure_summary_tables(
            self.ocp_test_provider_uuid, self.azure_test_provider_uuid, str(start_date), str(end_date)
        )
        mock_ocp_on_azure.assert_called_with(
            start_date,
            end_date,
            self.ocp_test_provider_uuid,
            self.azure_test_provider_uuid,
            cluster_id,
            bill_id,
            decimal.Decimal(0),
        )
