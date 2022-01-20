#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import patch

import pandas as pd
from tenant_schemas.utils import schema_context

from api.models import Provider
from api.utils import DateHelper
from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.azure_report_db_accessor import AzureReportDBAccessor
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.processor.parquet.ocp_cloud_parquet_report_processor import OCPCloudParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import OPENSHIFT_REPORT_TYPE
from masu.processor.parquet.parquet_report_processor import PARQUET_EXT
from masu.test import MasuTestCase
from masu.util.aws.common import match_openshift_resources_and_labels
from masu.util.gcp.common import match_openshift_resources_and_labels as gcp_match_openshift_resources_and_labels


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

    def test_ocp_infrastructure_map(self):
        """Test that the infra map is returned."""
        infra_map = self.report_processor.ocp_infrastructure_map
        infra_tuple = infra_map.get(str(self.ocp_on_aws_ocp_provider.uuid))
        self.assertIn(str(self.ocp_on_aws_ocp_provider.uuid), infra_map)
        self.assertEqual(self.aws_provider_uuid, infra_tuple[0])

        with patch.object(
            OCPCloudUpdaterBase, "get_openshift_and_infra_providers_lists"
        ) as mock_get_infra, patch.object(
            OCPCloudUpdaterBase, "_generate_ocp_infra_map_from_sql_trino"
        ) as mock_trino_get:
            mock_get_infra.return_value = ([], [])
            report_processor = OCPCloudParquetReportProcessor(
                schema_name=self.schema,
                report_path=self.report_path,
                provider_uuid=self.aws_provider_uuid,
                provider_type=Provider.PROVIDER_AWS_LOCAL,
                manifest_id=self.manifest_id,
                context={"request_id": self.request_id, "start_date": DateHelper().today, "create_table": True},
            )
            report_processor.ocp_infrastructure_map
            mock_trino_get.assert_called()

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
        df = pd.DataFrame()
        self.report_processor.create_ocp_on_cloud_parquet(df, base_file_name, 0, self.ocp_provider_uuid)
        mock_write.assert_called()
        expected = f"{file_path}/{self.ocp_provider_uuid}_0_{self.ocp_provider_uuid}{PARQUET_EXT}"
        mock_create_table.assert_called_with(expected, daily=True)

    @patch.object(OCPReportDBAccessor, "get_openshift_topology_for_provider")
    @patch.object(OCPCloudParquetReportProcessor, "create_ocp_on_cloud_parquet")
    @patch.object(OCPCloudParquetReportProcessor, "ocp_on_cloud_data_processor")
    def test_process(self, mock_data_processor, mock_create_parquet, mock_topology):
        """Test that ocp on cloud data is fully processed."""
        mock_topology.return_value = {"cluster_id": self.ocp_cluster_id}
        self.report_processor.process("", [pd.DataFrame()])

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
        )
        self.assertEqual(report_processor.ocp_on_cloud_data_processor, gcp_match_openshift_resources_and_labels)
