#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportProcessor object."""
from unittest.mock import patch

from api.models import Provider
from masu.processor.parquet.ocp_cloud_parquet_report_processor import OCPCloudParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.processor.report_processor import ReportProcessor
from masu.test import MasuTestCase


class ReportProcessorTest(MasuTestCase):
    """Test Cases for the ReportProcessor object."""

    @patch("masu.processor.report_processor.ParquetReportProcessor.process", return_value=(1, 1))
    @patch("masu.processor.report_processor.OCPCloudParquetReportProcessor.process", return_value=2)
    def test_aws_process(self, mock_ocp_cloud_process, mock_parquet_process):
        """Test to process for AWS."""
        processor = ReportProcessor(
            schema_name=self.schema_name,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "tracing_id": "1"},
        )
        processor.process()
        mock_parquet_process.assert_called()
        mock_ocp_cloud_process.assert_called()

    @patch("masu.processor.report_processor.ParquetReportProcessor.process", return_value=(1, []))
    @patch("masu.processor.report_processor.OCPCloudParquetReportProcessor.process", return_value=2)
    def test_aws_process_returns_false(self, mock_ocp_cloud_process, mock_parquet_process):
        """Test to check no data frames returned from process."""
        processor = ReportProcessor(
            schema_name=self.schema_name,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "tracing_id": "1"},
        )
        result = processor.process()
        self.assertFalse(result)

    def test_set_processor_parquet(self):
        """Test that the Parquet class is returned."""
        processor = ReportProcessor(
            schema_name=self.schema_name,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "request_id": 1},
        )
        self.assertIsInstance(processor._processor, ParquetReportProcessor)

    def test_ocp_on_cloud_processor(self):
        """Test that we return the right class."""

        processor = ReportProcessor(
            schema_name=self.schema_name,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "request_id": 1, "tracing_id": 2},
        )
        self.assertIsInstance(processor.ocp_on_cloud_processor, OCPCloudParquetReportProcessor)

        processor = ReportProcessor(
            schema_name=self.schema_name,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_OCP,
            provider_uuid=self.ocp_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "request_id": 1, "tracing_id": 3},
        )
        self.assertIsNone(processor.ocp_on_cloud_processor)
