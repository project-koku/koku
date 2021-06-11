#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportProcessor object."""
from unittest.mock import patch

from django.test import override_settings

from api.models import Provider
from masu.exceptions import MasuProcessingError
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.processor.report_processor import ReportProcessor
from masu.processor.report_processor import ReportProcessorError
from masu.test import MasuTestCase


class ReportProcessorTest(MasuTestCase):
    """Test Cases for the ReportProcessor object."""

    def test_initializer_aws(self):
        """Test to initializer for AWS."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    def test_initializer_aws_local(self):
        """Test to initializer for AWS-local."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS_LOCAL,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    def test_initializer_azure(self):
        """Test to initializer for Azure."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AZURE,
            provider_uuid=self.azure_provider_uuid,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    def test_initializer_ocp(self):
        """Test to initializer for OCP."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path=(
                "./koku/masu/test/data/ocp/" "e6b3701e-1e91-433b-b238-a31e49937558_February-2019-my-ocp-cluster-1.csv"
            ),
            compression="PLAIN",
            provider=Provider.PROVIDER_OCP,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    def test_initializer_azure_local(self):
        """Test to initializer for AZURE-local."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path=(
                "./koku/masu/test/data/ocp/" "e6b3701e-1e91-433b-b238-a31e49937558_February-2019-my-ocp-cluster-1.csv"
            ),
            compression="PLAIN",
            provider=Provider.PROVIDER_AZURE_LOCAL,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
        )
        self.assertIsNotNone(processor._processor)

    @patch("masu.processor.aws.aws_report_processor.AWSReportProcessor.__init__", side_effect=MasuProcessingError)
    def test_initializer_error(self, fake_processor):
        """Test to initializer with error."""
        with self.assertRaises(ReportProcessorError):
            ReportProcessor(
                schema_name=self.schema,
                report_path="/my/report/file",
                compression="GZIP",
                provider=Provider.PROVIDER_AWS,
                provider_uuid=self.aws_provider_uuid,
                manifest_id=None,
            )

    @patch("masu.processor.aws.aws_report_processor.AWSReportProcessor.__init__", side_effect=NotImplementedError)
    def test_initializer_not_implemented_error(self, fake_processor):
        """Test to initializer with error."""
        with self.assertRaises(NotImplementedError):
            ReportProcessor(
                schema_name=self.schema,
                report_path="/my/report/file",
                compression="GZIP",
                provider=Provider.PROVIDER_AWS,
                provider_uuid=self.aws_provider_uuid,
                manifest_id=None,
            )

    def test_initializer_invalid_provider(self):
        """Test to initializer with invalid provider."""
        with self.assertRaises(ReportProcessorError):
            ReportProcessor(
                schema_name=self.schema,
                report_path="/my/report/file",
                compression="GZIP",
                provider="unknown",
                provider_uuid=self.aws_provider_uuid,
                manifest_id=None,
            )

    @patch("masu.processor.aws.aws_report_processor.AWSReportProcessor.process", return_value=None)
    def test_aws_process(self, fake_process):
        """Test to process for AWS."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
        )
        try:
            processor.process()
        except Exception:
            self.fail("unexpected error")

    @patch("masu.processor.aws.aws_report_processor.AWSReportProcessor.process", side_effect=MasuProcessingError)
    def test_aws_process_error(self, fake_process):
        """Test to process for AWS with processing error."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
        )
        with self.assertRaises(ReportProcessorError):
            processor.process()

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
        )
        try:
            processor.remove_processed_files("/my/report/file")
        except Exception:
            self.fail("unexpected error")

    @patch(
        "masu.processor.aws.aws_report_processor.AWSReportProcessor.remove_temp_cur_files",
        side_effect=MasuProcessingError,
    )
    def test_aws_remove_processed_files_error(self, fake_process):
        """Test to remove_processed_files for AWS with processing error."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
        )
        with self.assertRaises(ReportProcessorError):
            processor.remove_processed_files("/my/report/file")

    @override_settings(ENABLE_PARQUET_PROCESSING=True)
    def test_set_processor_parquet(self):
        """Test that the Parquet class is returned."""
        processor = ReportProcessor(
            schema_name=self.schema,
            report_path="/my/report/file",
            compression="GZIP",
            provider=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
            manifest_id=None,
            context={"request_id": 1},
        )
        self.assertIsInstance(processor._processor, ParquetReportProcessor)
