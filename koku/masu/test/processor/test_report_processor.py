#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportProcessor object."""
from unittest.mock import patch

from api.models import Provider
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import ReportsAlreadyProcessed
from masu.processor.report_processor import ReportProcessor
from masu.test import MasuTestCase


class ReportProcessorTest(MasuTestCase):
    """Test Cases for the ReportProcessor object."""

    @patch("masu.processor.report_processor.ParquetReportProcessor.process", return_value=(1, 1))
    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    def test_aws_process(self, mock_status, mock_parquet_process):
        """Test to process for AWS."""
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
        mock_parquet_process.assert_called()

    @patch("masu.processor.report_processor.ParquetReportProcessor.process", return_value=None)
    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    def test_aws_process_returns_false(self, mock_status, mock_parquet_process):
        """Test to check no data frames returned from process."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "tracing_id": "1"},
        )
        result = processor.process()
        self.assertFalse(result)

    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    def test_set_processor_parquet(self, mock_status):
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

    @patch(
        "masu.processor.report_processor.ParquetReportProcessor.process",
        side_effect=ReportsAlreadyProcessed("test error"),
    )
    @patch("masu.processor._tasks.process.CostUsageReportStatus.objects")
    def test_ocp_process(self, mock_status, mock_parquet_process):
        """Test to process for AWS."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_OCP,
            provider_uuid=self.ocp_provider_uuid,
            manifest_id=None,
            context={"start_date": self.start_date, "tracing_id": "1"},
        )
        result = processor.process()
        mock_parquet_process.assert_called()
        self.assertTrue(result)
