#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportProcessor object."""
from unittest.mock import patch
from unittest.mock import PropertyMock

from api.models import Provider
from masu.processor.parquet.ocp_cloud_parquet_report_processor import OCPCloudParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.processor.report_processor import ReportProcessor
from masu.test import MasuTestCase


class ReportProcessorTest(MasuTestCase):
    """Test Cases for the ReportProcessor object."""

    @patch("masu.processor.report_processor.ReportProcessor.trino_enabled", new_callable=PropertyMock)
    @patch("masu.processor.report_processor.ParquetReportProcessor.process", return_value=(1, 1))
    @patch("masu.processor.report_processor.OCPCloudParquetReportProcessor.process", return_value=2)
    @patch("masu.processor.report_processor.AWSReportProcessor.process", return_value=1)
    def test_aws_process(self, mock_process, mock_ocp_cloud_process, mock_parquet_process, mock_trino_enabled):
        """Test to process for AWS."""
        mock_trino_enabled.return_value = True
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "tracing_id": "1"},
        )
        processor.process()
        mock_process.assert_not_called()
        mock_parquet_process.assert_called()
        mock_ocp_cloud_process.assert_called()

        mock_trino_enabled.reset_mock()
        mock_parquet_process.reset_mock()
        mock_ocp_cloud_process.reset_mock()
        mock_trino_enabled.return_value = False
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "tracing_id": "1"},
        )
        processor.process()
        mock_process.assert_called()
        mock_parquet_process.assert_not_called()
        mock_ocp_cloud_process.assert_not_called()

    @patch("masu.processor.aws.aws_report_processor.AWSReportProcessor.remove_temp_cur_files", return_value=None)
    def test_aws_remove_processed_files(self, fake_process):
        """Test to remove_processed_files for AWS."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "tracing_id": "1"},
        )
        try:
            processor.remove_processed_files("/my/report/file")
        except Exception:
            self.fail("unexpected error")

    def test_set_processor_parquet(self):
        """Test that the Parquet class is returned."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "request_id": 1},
        )
        self.assertIsInstance(processor._processor, ParquetReportProcessor)

    @patch("masu.processor.report_processor.ReportProcessor.trino_enabled", new_callable=PropertyMock)
    def test_ocp_on_cloud_processor(self, mock_trino_enabled):
        """Test that we return the right class."""
        mock_trino_enabled.return_value = True

        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "request_id": 1},
        )
        self.assertIsInstance(processor.ocp_on_cloud_processor, OCPCloudParquetReportProcessor)

        mock_trino_enabled.reset_mock()
        mock_trino_enabled.return_value = False

        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"request_id": 1},
        )
        self.assertIsNone(processor.ocp_on_cloud_processor)
