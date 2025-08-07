#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPCloudParquetReportSummaryUpdaterTest."""
import datetime
import decimal
from unittest.mock import Mock
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.db import IntegrityError
from django_tenants.utils import schema_context

from api.metrics.constants import DEFAULT_DISTRIBUTION_TYPE
from api.provider.models import Provider
from api.provider.models import ProviderInfrastructureMap
from koku.database import get_model
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import DELETE_TABLE
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import TRUNCATE_TABLE
from masu.test import MasuTestCase


class OCPCloudParquetReportSummaryUpdaterTest(MasuTestCase):
    """Test cases for the OCPCloudParquetReportSummaryUpdaterTest class."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.today = self.dh.today

    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map_from_providers")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_ui_summary_tables_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary_trino"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.aws_get_bills_from_provider")
    def test_update_aws_summary_tables(
        self,
        mock_utility,
        mock_ocp_on_aws,
        mock_ui_summary,
        mock_map,
        mock_cluster_info,
    ):
        """Test that summary tables are properly run for an OCP provider."""
        fake_bills = [Mock(id=1), Mock(id=2)]
        # this is a yes or no check so true is fine
        mock_cluster_info.return_value = True
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with OCPReportDBAccessor(self.schema_name) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(self.ocpaws_provider_uuid, start_date)
        with schema_context(self.schema_name):
            current_ocp_report_period_id = report_period.id

        mock_map.return_value = {self.ocpaws_provider_uuid: (self.aws_provider_uuid, Provider.PROVIDER_AWS)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)
        updater.update_aws_summary_tables(self.ocpaws_provider_uuid, self.aws_test_provider_uuid, start_date, end_date)
        mock_ocp_on_aws.assert_called_with(
            start_date,
            end_date,
            self.ocpaws_provider_uuid,
            self.aws_test_provider_uuid,
            current_ocp_report_period_id,
            1,
        )

    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider",
        return_value=True,
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.report_periods_for_provider_uuid",
        return_value=Mock(id=4),
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.delete_infrastructure_raw_cost_from_daily_summary"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.aws_get_bills_from_provider", return_value=False)
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.PartitionHandlerMixin._handle_partitions")
    def test_update_aws_summary_tables_no_billing_data(
        self,
        mock_handle_partitions,
        mock_aws_get_bills_from_provider,
        mock_delete_infrastructure_raw_cost_from_daily_summary,
        mock_report_periods_for_provider_uuid,
        mock_get_cluster_for_provider,
    ):
        """Test that AWS summary tables are not updated when no billing data is available"""
        mock_handle_partitions.side_effect = AttributeError(
            "Test failure. Should return before getting here when there is no AWS billing data"
        )

        start_date = datetime.datetime(2023, 5, 27, tzinfo=settings.UTC)
        end_date = start_date + datetime.timedelta(days=1)

        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)

        updater.update_aws_summary_tables(self.ocpaws_provider_uuid, self.aws_test_provider_uuid, start_date, end_date)

    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map_from_providers")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_tag_information"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_ui_summary_tables_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_cost_daily_summary_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.delete_line_item_daily_summary_entries_for_date_range_raw"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.azure_get_bills_from_provider")
    def test_update_azure_summary_tables(
        self,
        mock_utility,
        mock_delete,
        mock_ocpall_proj_summ,
        mock_ocpall_summ,
        mock_ocpall_persp,
        mock_ocp_on_azure,
        mock_ui_summary,
        mock_tag_summary,
        mock_map,
        mock_cluster_info,
    ):
        """Test that summary tables are properly run for an OCP provider."""
        fake_bills = [Mock(id=1), Mock(id=2)]
        # this is basically a yes or no check so true is fine
        mock_cluster_info.return_value = True
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with OCPReportDBAccessor(self.schema_name) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(self.ocpazure_provider_uuid, start_date)
        with schema_context(self.schema_name):
            current_ocp_report_period_id = report_period.id
        mock_map.return_value = {self.ocpazure_provider_uuid: (self.azure_provider_uuid, Provider.PROVIDER_AZURE)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.azure_provider, manifest=None)
        updater.update_azure_summary_tables(
            self.ocpazure_provider_uuid, self.azure_test_provider_uuid, start_date, end_date
        )
        mock_ocp_on_azure.assert_called_with(
            start_date,
            end_date,
            self.ocpazure_provider_uuid,
            self.azure_test_provider_uuid,
            current_ocp_report_period_id,
            1,
        )

    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map_from_providers")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_tag_information"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_ui_summary_tables_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_cost_daily_summary_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.delete_line_item_daily_summary_entries_for_date_range_raw"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.azure_get_bills_from_provider")
    def test_update_azure_summary_tables_with_string_dates(
        self,
        mock_utility,
        mock_delete,
        mock_ocpall_proj_summ,
        mock_ocpall_summ,
        mock_ocpall_persp,
        mock_ocp_on_azure,
        mock_ui_summary,
        mock_tag_summary,
        mock_map,
        mock_cluster_info,
    ):
        """Test that summary tables are properly run for an OCP provider."""
        fake_bills = [Mock(id=1), Mock(id=2)]
        # this is a yes or no check so true is fine
        mock_cluster_info.return_value = True
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with OCPReportDBAccessor(self.schema_name) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(self.ocpazure_provider_uuid, start_date)
        with schema_context(self.schema_name):
            current_ocp_report_period_id = report_period.id
        mock_map.return_value = {self.ocpazure_provider_uuid: (self.azure_provider_uuid, Provider.PROVIDER_AZURE)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.azure_provider, manifest=None)
        updater.update_azure_summary_tables(
            self.ocpazure_provider_uuid, self.azure_test_provider_uuid, str(start_date), str(end_date)
        )
        mock_ocp_on_azure.assert_called_with(
            start_date,
            end_date,
            self.ocpazure_provider_uuid,
            self.azure_test_provider_uuid,
            current_ocp_report_period_id,
            1,
        )

    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map_from_providers")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.populate_ocp_on_gcp_tag_information"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.populate_ocp_on_gcp_ui_summary_tables_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.populate_ocp_on_gcp_cost_daily_summary_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.back_populate_ocp_infrastructure_costs"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.delete_line_item_daily_summary_entries_for_date_range_raw"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.gcp_get_bills_from_provider")
    def test_update_gcp_summary_tables(
        self,
        mock_utility,
        mock_delete,
        mock_back_populate,
        mock_ocp_on_gcp,
        mock_ui_summary,
        mock_tag_summary,
        mock_map,
        mock_ocpallproj,
        mock_ocpall,
        mock_ocpallui,
    ):
        """Test that summary tables are properly run for a gcp provider."""
        fake_bills = [Mock(id=1), Mock(id=2)]
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with OCPReportDBAccessor(self.schema_name) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(self.ocpgcp_provider_uuid, start_date)
        with schema_context(self.schema_name):
            current_ocp_report_period_id = report_period.id
        mock_map.return_value = {self.ocpgcp_provider_uuid: (self.gcp_provider_uuid, Provider.PROVIDER_GCP)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.gcp_provider, manifest=None)
        updater.update_gcp_summary_tables(self.ocpgcp_provider_uuid, self.gcp_test_provider_uuid, start_date, end_date)
        mock_ocp_on_gcp.assert_called_with(
            start_date,
            end_date,
            self.ocpgcp_provider_uuid,
            self.gcp_test_provider_uuid,
            current_ocp_report_period_id,
            1,
        )
        mock_ui_summary.assert_called_with(
            start_date, end_date, self.ocpgcp_provider_uuid, self.gcp_test_provider_uuid
        )
        mock_tag_summary.assert_called_with([1, 2], start_date, end_date, current_ocp_report_period_id)

    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_ui_summary_tables"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_daily_summary"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.populate_ocp_on_all_project_daily_summary"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase.get_infra_map_from_providers")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.populate_ocp_on_gcp_tag_information"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.populate_ocp_on_gcp_ui_summary_tables_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.populate_ocp_on_gcp_cost_daily_summary_trino"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.back_populate_ocp_infrastructure_costs"  # noqa: E501
    )
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.GCPReportDBAccessor.delete_line_item_daily_summary_entries_for_date_range_raw"  # noqa: E501
    )
    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.gcp_get_bills_from_provider")
    def test_update_gcp_summary_tables_with_string_dates(
        self,
        mock_utility,
        mock_delete,
        mock_back_populate,
        mock_ocp_on_gcp,
        mock_ui_summary,
        mock_tag_summary,
        mock_map,
        mock_ocpallproj,
        mock_ocpall,
        mock_ocpallui,
    ):
        """Test that summary tables are properly run for a gcp provider."""
        fake_bills = [Mock(id=1), Mock(id=2)]
        mock_utility.return_value = fake_bills
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)

        with OCPReportDBAccessor(self.schema_name) as accessor:
            report_period = accessor.report_periods_for_provider_uuid(self.ocpgcp_provider_uuid, start_date)
        with schema_context(self.schema_name):
            current_ocp_report_period_id = report_period.id
        mock_map.return_value = {self.ocpgcp_provider_uuid: (self.gcp_provider_uuid, Provider.PROVIDER_GCP)}
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.gcp_provider, manifest=None)
        updater.update_gcp_summary_tables(
            self.ocpgcp_provider_uuid, self.gcp_test_provider_uuid, str(start_date), str(end_date)
        )
        mock_ocp_on_gcp.assert_called_with(
            start_date,
            end_date,
            self.ocpgcp_provider_uuid,
            self.gcp_test_provider_uuid,
            current_ocp_report_period_id,
            1,
        )
        mock_ui_summary.assert_called_with(
            start_date, end_date, self.ocpgcp_provider_uuid, self.gcp_test_provider_uuid
        )

        mock_tag_summary.assert_called_with([1, 2], start_date, end_date, current_ocp_report_period_id)

    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AzureReportDBAccessor.populate_ocp_on_azure_cost_daily_summary_trino"  # noqa: E501
    )
    def test_update_azure_summary_tables_with_no_cluster_info(self, mock_ocp_on_azure, mock_cluster_info):
        """Test that azure summary tables are not updated when there is no cluster info."""
        # this is a yes or no check so false is fine
        mock_cluster_info.return_value = False
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.azure_provider, manifest=None)
        updater.update_azure_summary_tables(
            self.ocpazure_provider_uuid, self.azure_test_provider_uuid, str(start_date), str(end_date)
        )
        mock_ocp_on_azure.assert_not_called()

    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider")
    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.populate_ocp_on_aws_cost_daily_summary_trino"  # noqa: E501
    )
    def test_update_aws_summary_tables_with_no_cluster_info(self, mock_ocp_on_aws, mock_cluster_info):
        """Test that aws summary tables are not updated when there is no cluster info."""
        # this is a yes or no check so false is fine
        mock_cluster_info.return_value = False
        start_date = self.dh.today.date()
        end_date = start_date + datetime.timedelta(days=1)
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)
        updater.update_aws_summary_tables(
            self.ocpaws_provider_uuid, self.aws_test_provider_uuid, str(start_date), str(end_date)
        )
        mock_ocp_on_aws.assert_not_called()

    def test_update_aws_summary_tables_no_report_period(self):
        start_date = "1900-12-30"
        end_date = "1900-12-31"
        with patch(
            "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider",
            return_value="goo-goo-cluster",
        ):
            updater = OCPCloudParquetReportSummaryUpdater(
                schema="org1234567", provider=self.aws_provider, manifest=None
            )
            with self.assertLogs("masu.processor.ocp.ocp_cloud_parquet_summary_updater", level="INFO") as _logger:
                updater.update_aws_summary_tables(
                    self.ocpaws_provider_uuid, self.aws_test_provider_uuid, start_date, end_date
                )
                found_it = False
                for log_line in _logger.output:
                    found_it = "No report period for AWS provider".lower() in log_line.lower()
                    if found_it:
                        break
                self.assertTrue(found_it)

    def test_update_azure_summary_tables_no_report_period(self):
        start_date = "1900-12-30"
        end_date = "1900-12-31"
        with patch(
            "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider",
            return_value="goo-goo-cluster",
        ):
            updater = OCPCloudParquetReportSummaryUpdater(
                schema="org1234567", provider=self.azure_provider, manifest=None
            )
            with self.assertLogs("masu.processor.ocp.ocp_cloud_parquet_summary_updater", level="INFO") as _logger:
                updater.update_azure_summary_tables(
                    self.ocpazure_provider_uuid, self.azure_test_provider_uuid, start_date, end_date
                )
                found_it = False
                for log_line in _logger.output:
                    found_it = "No report period for Azure provider".lower() in log_line.lower()
                    if found_it:
                        break
                self.assertTrue(found_it)

    def test_update_gcp_summary_tables_no_report_period(self):
        start_date = "1900-12-30"
        end_date = "1900-12-31"
        with patch(
            "masu.processor.ocp.ocp_cloud_parquet_summary_updater.OCPReportDBAccessor.get_cluster_for_provider",
            return_value="goo-goo-cluster",
        ):
            updater = OCPCloudParquetReportSummaryUpdater(
                schema="org1234567", provider=self.gcp_provider, manifest=None
            )
            with self.assertLogs("masu.processor.ocp.ocp_cloud_parquet_summary_updater", level="INFO") as _logger:
                updater.update_gcp_summary_tables(
                    self.ocpgcp_provider_uuid, self.gcp_test_provider_uuid, start_date, end_date
                )
                found_it = False
                for log_line in _logger.output:
                    found_it = "No report period for GCP provider".lower() in log_line.lower()
                    if found_it:
                        break
                self.assertTrue(found_it)

    def test_get_infra_map_from_providers(self):
        """Test that an infrastructure map is returned."""
        updater = OCPCloudParquetReportSummaryUpdater(
            schema=self.schema, provider=self.ocp_on_aws_ocp_provider, manifest=None
        )

        expected_mapping = (self.aws_provider_uuid, Provider.PROVIDER_AWS_LOCAL)
        infra_map = updater.get_infra_map_from_providers()
        self.assertEqual(len(infra_map.keys()), 1)
        self.assertIn(str(self.ocp_on_aws_ocp_provider.uuid), infra_map)
        self.assertEqual(infra_map.get(str(self.ocp_on_aws_ocp_provider.uuid)), expected_mapping)

        updater = OCPCloudParquetReportSummaryUpdater(schema=self.schema, provider=self.aws_provider, manifest=None)

        infra_map = updater.get_infra_map_from_providers()

        self.assertEqual(len(infra_map.keys()), 1)
        self.assertIn(str(self.ocp_on_aws_ocp_provider.uuid), infra_map)
        self.assertEqual(infra_map.get(str(self.ocp_on_aws_ocp_provider.uuid)), expected_mapping)

    def test_get_infra_map_from_providers_delete_incorrect_ocp(self):
        """Test that an infrastructure map of type OCP is deleted."""
        p1 = self.baker.make("Provider", type=Provider.PROVIDER_OCP)
        pm = self.baker.make("ProviderInfrastructureMap", infrastructure_type=p1.type, infrastructure_provider=p1)
        p: Provider = self.baker.make("Provider", type=Provider.PROVIDER_OCP, infrastructure=pm)
        self.assertIsNotNone(p.infrastructure)

        updater = OCPCloudParquetReportSummaryUpdater(schema=self.schema, provider=p, manifest=None)
        self.assertFalse(updater.get_infra_map_from_providers())

        p.refresh_from_db()
        self.assertIsNone(p.infrastructure)

    def test_set_provider_infra_map(self):
        """Test set_provider_infra_map."""
        infra_uuid = self.aws_provider_uuid
        infra_type = self.aws_provider.type
        p: Provider = self.baker.make("Provider", type=Provider.PROVIDER_OCP)

        infra_map = {str(p.uuid): (infra_uuid, infra_type)}
        expected_infra = ProviderInfrastructureMap.objects.get(infrastructure_provider_id=infra_uuid)

        updater = OCPCloudParquetReportSummaryUpdater(schema=self.schema, provider=p, manifest=None)
        updater.set_provider_infra_map(infra_map)

        p.refresh_from_db()
        self.assertEqual(p.infrastructure, expected_infra)

    def test_set_provider_infra_map_unknown_provider(self):
        """Test set_provider_infra_map does not raise exception for unknown provider."""
        infra_uuid = self.aws_provider_uuid
        infra_type = self.aws_provider.type
        infra_map = {self.unkown_test_provider_uuid: (infra_uuid, infra_type)}
        updater = OCPCloudParquetReportSummaryUpdater(schema=self.schema, provider=self.aws_provider, manifest=None)
        try:
            updater.set_provider_infra_map(infra_map)
        except Exception:
            self.fail("set_provider_infra_map should not fail on unknown provider")

    @patch("masu.processor.ocp.ocp_cloud_updater_base.ProviderInfrastructureMap.objects")
    def test_set_provider_infra_map_providermap_integrity_error_race(self, mock_map):
        """Test set_provider_infra_map does not raise exception when providermap is not found."""
        infra_uuid = self.aws_provider_uuid
        infra_type = self.aws_provider.type
        p: Provider = self.baker.make("Provider", type=Provider.PROVIDER_OCP)

        mock_map.get_or_create.side_effect = IntegrityError()
        mock_map.filter.return_value.first.return_value = None

        infra_map = {str(p.uuid): (infra_uuid, infra_type)}

        updater = OCPCloudParquetReportSummaryUpdater(schema=self.schema, provider=p, manifest=None)
        try:
            updater.set_provider_infra_map(infra_map)
        except Exception:
            self.fail("set_provider_infra_map should not fail when map not found")

    def test_set_provider_infra_map_providermap_integrity_error_filter(self):
        """Test set_provider_infra_map during race condition creating map."""
        infra_uuid = self.aws_provider_uuid
        infra_type = self.aws_provider.type
        p: Provider = self.baker.make("Provider", type=Provider.PROVIDER_OCP)
        expected_infra = ProviderInfrastructureMap.objects.get(infrastructure_provider_id=infra_uuid)

        infra_map = {str(p.uuid): (infra_uuid, infra_type)}
        updater = OCPCloudParquetReportSummaryUpdater(schema=self.schema, provider=p, manifest=None)
        with patch("masu.processor.ocp.ocp_cloud_updater_base.ProviderInfrastructureMap.objects") as mock_map:
            mock_map.get_or_create.side_effect = IntegrityError()
            mock_map.filter.return_value.first.return_value = expected_infra
            updater.set_provider_infra_map(infra_map)

            p.refresh_from_db()
            self.assertEqual(p.infrastructure, expected_infra)

    def test_partition_handler_str_table(self):
        new_table_sql = f"""
create table {self.schema}._eek_pt0 (usage_start date not null, id int) partition by range (usage_start);
"""
        with schema_context(self.schema):
            with connection.cursor() as cur:
                cur.execute(new_table_sql)

            partable = get_model("PartitionedTable")
            default_part = partable(
                schema_name=self.schema,
                table_name="_eek_pt0_default",
                partition_of_table_name="_eek_pt0",
                partition_type=partable.RANGE,
                partition_col="usage_start",
                partition_parameters={"default": True},
                active=True,
            )
            default_part.save()

            ocrsu = OCPCloudParquetReportSummaryUpdater(self.schema, self.ocp_on_aws_ocp_provider, None)
            num_eek = partable.objects.filter(schema_name=self.schema, partition_of_table_name="_eek_pt0").count()
            self.assertEqual(num_eek, 1)

            ocrsu._handle_partitions(self.schema, "_eek_pt0", datetime.date(1970, 10, 1), datetime.date(1970, 12, 1))
            eek_p = partable.objects.filter(
                schema_name=self.schema, partition_of_table_name="_eek_pt0", partition_parameters__default=False
            ).all()
            self.assertEqual(len(eek_p), 3)

            eek_p.delete()
            default_part.delete()

            with connection.cursor() as cur:
                cur.execute(f"drop table {self.schema}._eek_pt0 ;")

    def test_can_truncate(self):
        """Test that we successfully determine if truncate can occur."""
        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)

        self.assertTrue(updater._can_truncate(start_date, end_date))

        end_date = end_date - datetime.timedelta(days=1)
        self.assertFalse(updater._can_truncate(start_date, end_date))

        end_date = self.dh.last_month_end
        # Fake a second aws source with an OCP cluster
        self.ocp_on_azure_ocp_provider.infrastructure.infrastructure_type = Provider.PROVIDER_AWS_LOCAL
        self.ocp_on_azure_ocp_provider.infrastructure.save()
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)
        # If we have more than one source providing OCP on AWS data, we can't truncate
        # as this would wipe the data for other sources that we may not be re-summarizing
        self.assertFalse(updater._can_truncate(start_date, end_date))

    def test_determine_truncates_and_deletes(self):
        """Test that we successfully determine if truncate can occur."""
        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)

        results = updater.determine_truncates_and_deletes(start_date, end_date)
        for value in results.values():
            self.assertEqual(value, TRUNCATE_TABLE)

        end_date = end_date - datetime.timedelta(days=1)
        results = updater.determine_truncates_and_deletes(start_date, end_date)
        for value in results.values():
            self.assertEqual(value, DELETE_TABLE)

    @patch(
        "masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.delete_line_item_daily_summary_entries_for_date_range_raw"  # noqa: E501
    )
    def test_delete_summary_table_data(self, mock_delete):
        """Test that the method calls the underlying db accessor delete call."""
        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)
        updater.delete_summary_table_data(start_date, end_date, "table")
        mock_delete.assert_called()

    @patch("masu.processor.ocp.ocp_cloud_parquet_summary_updater.AWSReportDBAccessor.truncate_partition")  # noqa: E501
    def test_truncate_summary_table_data(self, mock_truncate):
        """Test that the method calls the underlying db accessor truncate call."""
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)
        updater.truncate_summary_table_data("table_2023_03")
        mock_truncate.assert_called()

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_get_infra_map_ocp(self, mock_infra_map):
        """Test getting infra map for ocp on cloud provider"""
        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.ocp_provider, manifest=None)
        expected_infra_map = {self.ocp_provider_uuid: ("infra_provider_uuid", "infra_provider_type")}
        mock_infra_map.return_value = expected_infra_map
        infra_map = updater._generate_ocp_infra_map_from_sql_trino(start_date, end_date)
        self.assertIn(self.ocp_provider_uuid, str(infra_map))

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_get_infra_map_aws(self, mock_infra_map):
        """Test getting infra map for ocp on cloud provider"""
        start_date = self.dh.last_month_start
        end_date = self.dh.last_month_end
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)
        mock_infra_map.return_value = updater.get_infra_map_from_providers()
        infra_map = updater._generate_ocp_infra_map_from_sql_trino(start_date, end_date)
        self.assertIn(self.aws_provider_uuid, str(infra_map))
