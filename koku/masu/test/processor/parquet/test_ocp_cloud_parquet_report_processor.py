#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import ANY
from unittest.mock import patch

import pandas as pd
from django_tenants.utils import schema_context

from api.models import Provider
from api.utils import DateHelper
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.parquet.ocp_cloud_parquet_report_processor import OCPCloudParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import OPENSHIFT_REPORT_TYPE
from masu.processor.parquet.parquet_report_processor import PARQUET_EXT
from masu.processor.parquet.summary_sql_metadata import SummarySqlMetadata
from masu.test import MasuTestCase
from masu.util.aws.common import match_openshift_resources_and_labels
from masu.util.gcp.common import match_openshift_resources_and_labels as gcp_match_openshift_resources_and_labels
from reporting.provider.all.models import EnabledTagKeys
from reporting_common.models import CostUsageReportStatus


class TestOCPCloudParquetReportProcessor(MasuTestCase):
    """Test cases for OCPCloudParquetReportProcessor."""

    def setUp(self):
        """Set up shared test variables."""
        super().setUp()
        self.test_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        self.test_etag = "fake_etag"
        self.request_id = 1
        self.account_id = self.schema[4:]
        self.manifest_id = 1
        self.report_name = "koku-1.csv.gz"
        self.report_path = f"/my/{self.test_assembly_id}/{self.report_name}"
        self.start_date = DateHelper().today
        self.report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.aws_provider_uuid,
            provider_type=Provider.PROVIDER_AWS_LOCAL,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": self.start_date, "create_table": True},
        )

    def test_parquet_ocp_on_cloud_path_s3(self):
        """Test that the path is set properly."""
        self.assertIn(OPENSHIFT_REPORT_TYPE, self.report_processor.parquet_ocp_on_cloud_path_s3)

    def test_report_type(self):
        """Test that the report type is set properly."""
        self.assertEqual(OPENSHIFT_REPORT_TYPE, self.report_processor.report_type)

    def test_ocp_on_cloud_data_processor(self):
        """Test that the processor is properly set."""
        self.assertEqual(self.report_processor.ocp_on_cloud_data_processor, match_openshift_resources_and_labels)

        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.ocp_provider_uuid,
            provider_type=Provider.PROVIDER_OCP,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": DateHelper().today, "create_table": True},
        )
        self.assertIsNone(report_processor.ocp_on_cloud_data_processor)

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_ocp_infrastructure_map(self, mock_trino_get):
        """Test that the infra map is returned."""
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)
        mock_trino_get.return_value = updater.get_infra_map_from_providers()
        infra_map = self.report_processor.ocp_infrastructure_map
        infra_tuple = infra_map.get(str(self.ocp_on_aws_ocp_provider.uuid))
        self.assertIn(str(self.ocp_on_aws_ocp_provider.uuid), infra_map)
        self.assertEqual(self.aws_provider_uuid, infra_tuple[0])

        with patch.object(OCPCloudUpdaterBase, "get_openshift_and_infra_providers_lists") as mock_get_infra:
            mock_get_infra.return_value = ([], [])
            report_processor = OCPCloudParquetReportProcessor(
                schema_name=self.schema,
                report_path=self.report_path,
                provider_uuid=self.aws_provider_uuid,
                provider_type=Provider.PROVIDER_AWS_LOCAL,
                manifest_id=self.manifest_id,
                context={"request_id": self.request_id, "start_date": DateHelper().today, "create_table": True},
            )
            res = report_processor.ocp_infrastructure_map
            self.assertEqual(res, infra_map)
            mock_trino_get.assert_called()

    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_ocp_infrastructure_map_not_cloud(self, mock_trino_get):
        """Test that the infra map is returned."""
        with patch.object(OCPCloudUpdaterBase, "get_openshift_and_infra_providers_lists") as mock_get_infra:
            mock_get_infra.return_value = ([], [])
            report_processor = OCPCloudParquetReportProcessor(
                schema_name=self.schema,
                report_path=self.report_path,
                provider_uuid=self.ocp_provider_uuid,
                provider_type=Provider.PROVIDER_OCP,
                manifest_id=self.manifest_id,
                context={"request_id": self.request_id, "start_date": DateHelper().today, "create_table": True},
            )
            report_processor.ocp_infrastructure_map
            mock_trino_get.assert_not_called()

    def test_db_accessor(self):
        """Test that the correct class is returned."""
        self.assertIsInstance(self.report_processor.db_accessor, AWSReportDBAccessor)

        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.azure_provider_uuid,
            provider_type=Provider.PROVIDER_AZURE,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": DateHelper().today, "create_table": True},
        )
        self.assertIsInstance(report_processor.db_accessor, AzureReportDBAccessor)

        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.gcp_provider_uuid,
            provider_type=Provider.PROVIDER_GCP,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": DateHelper().today, "create_table": True},
        )
        self.assertIsInstance(report_processor.db_accessor, GCPReportDBAccessor)

        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.ocp_provider_uuid,
            provider_type=Provider.PROVIDER_OCP,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": DateHelper().today, "create_table": True},
        )
        self.assertIsNone(report_processor.db_accessor)

    def test_bill_id(self):
        """Test the bill id property."""
        with schema_context(self.schema_name):
            bills = self.report_processor.db_accessor.bills_for_provider_uuid(self.aws_provider_uuid, self.start_date)
            expected = bills.first().id

        self.assertEqual(self.report_processor.bill_id, expected)

    def test_has_enabled_ocp_labels(self):
        """Test that we return whether there are enabled labels"""
        with schema_context(self.schema_name):
            expected = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).exists()

        self.assertEqual(self.report_processor.has_enabled_ocp_labels, expected)

    def test_get_report_period_id(self):
        """Test that the OpenShift cluster's report period ID is returned."""
        with OCPReportDBAccessor(self.schema_name) as accessor:
            with schema_context(self.schema_name):
                report_period = accessor.report_periods_for_provider_uuid(self.ocp_provider_uuid, self.start_date)
                expected = report_period.id
        self.assertEqual(self.report_processor.get_report_period_id(self.ocp_provider_uuid), expected)

    def test_determin_s3_path(self):
        """Test that we return the OCP on cloud path."""
        self.assertEqual(
            self.report_processor._determin_s3_path(OPENSHIFT_REPORT_TYPE),
            self.report_processor.parquet_ocp_on_cloud_path_s3,
        )
        self.assertIsNone(self.report_processor._determin_s3_path("incorrect"))

    @patch.object(OCPCloudParquetReportProcessor, "create_parquet_table")
    @patch.object(OCPCloudParquetReportProcessor, "_write_parquet_to_file")
    def test_create_ocp_on_cloud_parquet(self, mock_write, mock_create_table):
        """Test that we write OCP on Cloud data and create a table."""
        base_file_name = f"{self.ocp_provider_uuid}"
        file_path = f"{self.report_processor.local_path}"
        df = pd.DataFrame({"test": [1, 2, 3]})
        self.report_processor.create_ocp_on_cloud_parquet(df, base_file_name)
        mock_write.assert_called()
        expected = f"{file_path}/{self.ocp_provider_uuid}{PARQUET_EXT}"
        mock_create_table.assert_called_with(expected, daily=True, partition_map=None)

    @patch.object(OCPCloudParquetReportProcessor, "create_parquet_table")
    @patch.object(OCPCloudParquetReportProcessor, "_write_parquet_to_file")
    def test_create_ocp_on_cloud_parquet_gcp_valid_idx(self, mock_write, mock_create_table):
        """Test that we write OCP on Cloud data for a GCP provider and create a table."""
        test_date = "2023-01-01"
        base_file_name = f"{self.gcp_provider_uuid}_{test_date}"
        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.gcp_provider_uuid,
            provider_type=Provider.PROVIDER_GCP_LOCAL,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": self.start_date, "create_table": True},
        )
        file_path = f"{report_processor.local_path}"
        invoice_month = "202301"
        df = pd.DataFrame({"test": [1], "invoice_month": [invoice_month]})
        report_processor.create_ocp_on_cloud_parquet(df, base_file_name)
        mock_write.assert_called()
        expected = f"{file_path}/{invoice_month}_{base_file_name}{PARQUET_EXT}"
        mock_create_table.assert_called_with(
            expected,
            daily=True,
            partition_map={"source": "varchar", "year": "varchar", "month": "varchar", "day": "varchar"},
        )

    @patch.object(OCPCloudParquetReportProcessor, "create_ocp_on_cloud_parquet")
    def test_create_partitioned_ocp_on_cloud_parquet_gcp(self, mock_create_table):
        """Test that we write partitioned OCP on Cloud data and create a table."""
        test_date = "2023-01-01"
        invoice_month = "202301"
        base_file_name = f"{invoice_month}_{test_date}_{self.gcp_provider_uuid}"
        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.gcp_provider_uuid,
            provider_type=Provider.PROVIDER_GCP_LOCAL,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": self.start_date, "create_table": True},
        )
        df = pd.DataFrame({"test": [1], "invoice_month": [invoice_month], "usage_start_time": "2023-01-01"})
        report_processor.create_partitioned_ocp_on_cloud_parquet(df, base_file_name)
        mock_create_table.assert_called_once()
        args, kwargs = mock_create_table.call_args
        call_df, call_base_file_name = args
        self.assertTrue(call_df.equals(df))
        self.assertEqual(base_file_name, f"{invoice_month}_{call_base_file_name}")

    @patch.object(OCPCloudParquetReportProcessor, "create_ocp_on_cloud_parquet")
    def test_create_partitioned_ocp_on_cloud_parquet_azure(self, mock_create_table):
        """Test that we write partitioned OCP on Cloud data and create a table."""
        test_date = "2023-01-01"
        base_file_name = f"{test_date}_{self.azure_provider_uuid}"
        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.azure_provider_uuid,
            provider_type=Provider.PROVIDER_AZURE_LOCAL,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": self.start_date, "create_table": True},
        )
        df = pd.DataFrame({"test": [1], "date": "2023-01-01"})
        report_processor.create_partitioned_ocp_on_cloud_parquet(df, base_file_name)
        mock_create_table.assert_called_once()
        args, kwargs = mock_create_table.call_args
        call_df, call_base_file_name = args
        self.assertTrue(call_df.equals(df))
        self.assertEqual(base_file_name, f"{call_base_file_name}")

    @patch.object(AWSReportDBAccessor, "get_openshift_on_cloud_matched_tags_trino")
    @patch.object(OCPReportDBAccessor, "get_cluster_for_provider")
    @patch.object(OCPReportDBAccessor, "get_openshift_topology_for_multiple_providers")
    @patch.object(OCPCloudParquetReportProcessor, "create_partitioned_ocp_on_cloud_parquet")
    @patch.object(OCPCloudParquetReportProcessor, "ocp_on_cloud_data_processor")
    @patch.object(OCPCloudParquetReportProcessor, "get_ocp_provider_uuids_tuple")
    def test_process(
        self,
        mock_ocp_uuids,
        mock_data_processor,
        mock_create_parquet,
        mock_topology,
        mock_cluster_info,
        mock_trino_tags,
    ):
        """Test that ocp on cloud data is fully processed."""
        # this is a yes or no check so true is fine
        mock_ocp_uuids.return_value = [self.ocp_provider_uuid]
        mock_cluster_info.return_value = True
        mock_topology.return_value = {"cluster_id": self.ocp_cluster_id}
        self.report_processor.process("", [pd.DataFrame()])

        mock_topology.assert_called()
        mock_data_processor.assert_called()
        mock_create_parquet.assert_called()

    @patch.object(GCPReportDBAccessor, "get_openshift_on_cloud_matched_tags_trino")
    @patch.object(OCPReportDBAccessor, "get_cluster_for_provider")
    @patch.object(OCPReportDBAccessor, "get_filtered_openshift_topology_for_multiple_providers")
    @patch.object(OCPCloudParquetReportProcessor, "create_partitioned_ocp_on_cloud_parquet")
    @patch.object(OCPCloudParquetReportProcessor, "ocp_on_cloud_data_processor")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_process_gcp(
        self,
        mock_infra_map,
        mock_data_processor,
        mock_create_parquet,
        mock_topology,
        mock_cluster_info,
        mock_trino_tags,
    ):
        """Test that ocp on cloud data is fully processed for a gcp provider."""
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.gcp_provider, manifest=None)
        mock_infra_map.return_value = updater.get_infra_map_from_providers()
        # this is a yes or no check so true is fine
        mock_cluster_info.return_value = True
        mock_topology.return_value = [{"cluster_id": self.ocpgcp_ocp_cluster_id}]
        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.gcp_provider_uuid,
            provider_type=Provider.PROVIDER_GCP,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": self.start_date, "create_table": True},
        )
        report_processor.process("", [pd.DataFrame()])

        mock_topology.assert_called()
        mock_data_processor.assert_called()
        mock_create_parquet.assert_called()

    def test_ocp_on_gcp_data_processor(self):
        """Test that the processor is properly set."""
        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.gcp_provider_uuid,
            provider_type=Provider.PROVIDER_GCP,
            manifest_id=self.manifest_id,
            context={"start_date": self.start_date, "tracing_id": "1"},
        )
        self.assertEqual(report_processor.ocp_on_cloud_data_processor, gcp_match_openshift_resources_and_labels)

    @patch.object(OCPReportDBAccessor, "get_cluster_for_provider")
    @patch.object(OCPCloudParquetReportProcessor, "create_ocp_on_cloud_parquet")
    @patch.object(OCPCloudParquetReportProcessor, "ocp_on_cloud_data_processor")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_process_no_cluster_info(
        self, mock_infra_map, mock_data_processor, mock_create_parquet, mock_cluster_info
    ):
        """Test that ocp on cloud data is not processed when there is no cluster info."""
        updater = OCPCloudParquetReportSummaryUpdater(schema="org1234567", provider=self.aws_provider, manifest=None)
        mock_infra_map.return_value = updater.get_infra_map_from_providers()
        # this is a yes or no check so false is fine
        mock_cluster_info.return_value = False
        self.report_processor.process("", [pd.DataFrame()])
        mock_data_processor.assert_not_called()
        mock_create_parquet.assert_not_called()

    @patch.object(OCPReportDBAccessor, "get_cluster_for_provider")
    @patch.object(OCPReportDBAccessor, "get_openshift_topology_for_multiple_providers")
    @patch.object(OCPCloudParquetReportProcessor, "has_enabled_ocp_labels")
    @patch.object(OCPCloudParquetReportProcessor, "get_ocp_provider_uuids_tuple")
    def test_process_no_data_frames(self, mock_ocp_uuids, mock_has_labels, mock_topology, mock_cluster_info):
        """Test that ocp on cloud data is not processed when there is no data framse."""
        expected = f"no OCP on {Provider.PROVIDER_AWS} daily frames to processes, skipping"
        mock_ocp_uuids.return_value = [self.ocp_provider_uuid]
        with self.assertLogs("masu.processor.parquet.ocp_cloud_parquet_report_processor", level="INFO") as logger:
            mock_cluster_info.return_value = True
            mock_has_labels.return_value = False
            mock_topology.return_value = {"cluster_id": self.ocp_cluster_id}
            self.report_processor.process("", [])
            self.assertIn(expected, str(logger))

    @patch.object(OCPReportDBAccessor, "get_cluster_for_provider")
    @patch.object(OCPReportDBAccessor, "get_openshift_topology_for_multiple_providers")
    @patch.object(OCPCloudParquetReportProcessor, "has_enabled_ocp_labels")
    @patch.object(OCPCloudParquetReportProcessor, "create_ocp_on_cloud_parquet")
    @patch.object(OCPCloudParquetReportProcessor, "ocp_on_cloud_data_processor")
    def process_no_enabled_ocp_labels(
        self, mock_data_processor, mock_create_parquet, mock_has_labels, mock_topology, mock_cluster_info
    ):
        """Test that process succeeds without OCP enabled labels"""
        mock_cluster_info.return_value = True
        mock_has_labels.return_value = False
        mock_topology.return_value = {"cluster_id": self.ocp_cluster_id}
        self.report_processor.process("", [pd.DataFrame()])

        mock_topology.assert_called()
        mock_data_processor.assert_called()
        mock_create_parquet.assert_called()

    @patch.object(GCPReportDBAccessor, "get_openshift_on_cloud_matched_tags_trino")
    @patch.object(GCPReportDBAccessor, "get_openshift_on_cloud_matched_tags")
    @patch.object(OCPReportDBAccessor, "get_cluster_for_provider")
    @patch.object(OCPReportDBAccessor, "get_openshift_topology_for_multiple_providers")
    @patch.object(OCPCloudParquetReportProcessor, "has_enabled_ocp_labels")
    @patch.object(OCPCloudParquetReportProcessor, "create_ocp_on_cloud_parquet")
    @patch.object(OCPCloudParquetReportProcessor, "ocp_on_cloud_data_processor")
    def process_enabled_ocp_labels_no_matches_with_gcp(
        self,
        mock_data_processor,
        mock_create_parquet,
        mock_has_labels,
        mock_topology,
        mock_cluster_info,
        gcp_tags,
        gcp_trino,
    ):
        """Test that process succeeds without OCP enabled labels"""
        gcp_tags.return_value = "skip"
        mock_cluster_info.return_value = True
        mock_has_labels.return_value = True
        mock_topology.return_value = {"cluster_id": self.ocp_cluster_id}
        self.report_processor.process("", [pd.DataFrame()])

        mock_topology.assert_called()
        mock_data_processor.assert_called()
        mock_create_parquet.assert_called()
        gcp_trino.assert_not_called()

    @patch.object(OCPReportDBAccessor, "get_openshift_on_cloud_matched_tags")
    @patch.object(OCPReportDBAccessor, "get_cluster_for_provider")
    @patch.object(OCPReportDBAccessor, "get_openshift_topology_for_multiple_providers")
    @patch.object(OCPCloudParquetReportProcessor, "has_enabled_ocp_labels")
    @patch.object(OCPCloudParquetReportProcessor, "create_ocp_on_cloud_parquet")
    @patch.object(OCPCloudParquetReportProcessor, "ocp_on_cloud_data_processor")
    def process_no_postgres_matched_tags(
        self,
        mock_data_processor,
        mock_create_parquet,
        mock_has_labels,
        mock_topology,
        mock_cluster_info,
        mock_matched_tags,
    ):
        """Test that process succeeds without OCP enabled labels"""
        mock_cluster_info.return_value = True
        mock_has_labels.return_value = True
        mock_matched_tags.return_value = []
        mock_topology.return_value = {"cluster_id": self.ocp_cluster_id}

        expected = "Matched tags not yet available via Postgres. Getting matching tags from Trino."
        with self.assertLogs("masu.processor.parquet.ocp_cloud_parquet_report_processor", level="INFO") as logger:
            self.report_processor.process("", [pd.DataFrame()])
            self.assertIn(expected, str(logger))

        mock_topology.assert_called()
        mock_data_processor.assert_called()
        mock_create_parquet.assert_called()

    @patch.object(AWSReportDBAccessor, "get_openshift_on_cloud_matched_tags_trino")
    @patch.object(AWSReportDBAccessor, "get_openshift_on_cloud_matched_tags")
    @patch.object(AWSReportDBAccessor, "check_for_matching_enabled_keys")
    @patch.object(OCPCloudParquetReportProcessor, "has_enabled_ocp_labels")
    def test_get_matched_tags(self, mock_has_enabled, mock_matching_enabled, mock_get_tags, mock_get_tags_trino):
        """Test that we get matched tags, cached if available."""

        mock_has_enabled.return_value = True
        mock_matching_enabled.return_Value = True

        self.report_processor.get_matched_tags([])
        mock_get_tags.assert_called()
        mock_get_tags_trino.assert_not_called()

        matched_tags = [{"tag_one": "value_one"}, {"tag_two": "value_bananas"}]
        mock_get_tags.reset_mock()
        with patch(
            "masu.processor.parquet.ocp_cloud_parquet_report_processor.get_value_from_cache",
            return_value=matched_tags,
        ):
            self.report_processor.get_matched_tags([])
            mock_get_tags.assert_not_called()

    @patch.object(AWSReportDBAccessor, "get_openshift_on_cloud_matched_tags_trino")
    @patch.object(AWSReportDBAccessor, "get_openshift_on_cloud_matched_tags")
    @patch.object(AWSReportDBAccessor, "check_for_matching_enabled_keys")
    @patch.object(OCPCloudParquetReportProcessor, "has_enabled_ocp_labels")
    def test_get_matched_tags_trino(self, mock_has_enabled, mock_matching_enabled, mock_get_tags, mock_get_tags_trino):
        """Test that we get matched tags, cached if available."""

        mock_has_enabled.return_value = True
        mock_matching_enabled.return_Value = True
        mock_get_tags.return_value = []

        self.report_processor.get_matched_tags([])
        mock_get_tags.assert_called()
        mock_get_tags_trino.assert_called()

        matched_tags = [{"tag_one": "value_one"}, {"tag_two": "value_bananas"}]
        mock_get_tags.reset_mock()
        with patch(
            "masu.processor.parquet.ocp_cloud_parquet_report_processor.get_value_from_cache",
            return_value=matched_tags,
        ):
            self.report_processor.get_matched_tags([])
            mock_get_tags.assert_not_called()

    @patch.object(AWSReportDBAccessor, "check_for_matching_enabled_keys", return_value=True)
    @patch.object(OCPCloudParquetReportProcessor, "has_enabled_ocp_labels", return_value=True)
    @patch.object(AWSReportDBAccessor, "get_openshift_on_cloud_matched_tags", return_value=None)
    @patch("masu.processor.parquet.ocp_cloud_parquet_report_processor.is_tag_processing_disabled", return_value=True)
    def test_get_matched_tags_trino_disabled(
        self, mock_unleash, mock_pg_tags, mock_has_enabled, mock_matching_enabled
    ):
        """Test that we skip trino matched tag queries if disabled in unleash."""
        result = self.report_processor.get_matched_tags([])
        self.assertEqual(result, [])

    def test_instantiating_processor_without_manifest_id(self):
        """Assert that report_status exists and is None."""
        report_processor = OCPCloudParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.gcp_provider_uuid,
            provider_type=Provider.PROVIDER_GCP_LOCAL,
            manifest_id=0,
            context={"request_id": self.request_id, "start_date": self.start_date, "create_table": True},
        )
        self.assertIsNone(report_processor.report_status)

    def test_instantiating_processor_with_manifest_id(self):
        """Assert that report_status exists and is not None."""
        self.assertIsNotNone(self.report_processor.report_status)
        self.assertIsInstance(self.report_processor.report_status, CostUsageReportStatus)

    def test_process_ocp_cloud_trino(self):
        """Test that processing ocp on cloud via trino calls the expected functions."""
        start_date = "2024-08-01"
        end_date = "2024-08-05"
        matched_tags = []
        managed_sql_params = SummarySqlMetadata(
            ANY, self.ocp_provider_uuid, self.aws_provider_uuid, start_date, end_date, matched_tags
        )
        with patch(
            (
                "masu.processor.parquet.ocp_cloud_parquet_report_processor"
                ".OCPCloudParquetReportProcessor.get_ocp_provider_uuids_tuple"
            ),
            return_value=self.ocp_provider_uuid,
        ), patch(
            "masu.processor.parquet.ocp_cloud_parquet_report_processor.OCPCloudParquetReportProcessor.get_matched_tags",
            return_value=matched_tags,
        ), patch(
            "masu.processor.parquet.ocp_cloud_parquet_report_processor.OCPCloudParquetReportProcessor.db_accessor"
        ) as accessor:
            rp = OCPCloudParquetReportProcessor(
                schema_name=self.schema,
                report_path=self.report_path,
                provider_uuid=self.aws_provider_uuid,
                provider_type=Provider.PROVIDER_AWS_LOCAL,
                manifest_id=self.manifest_id,
                context={"request_id": self.request_id, "start_date": self.start_date, "create_table": True},
            )
            rp.process_ocp_cloud_trino(self.ocp_provider_uuid, start_date, end_date)
            accessor.populate_ocp_on_cloud_daily_trino.assert_called_with(managed_sql_params)
