#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for OCP parquet post-write deduplication (COST-7469)."""
import logging
from pathlib import Path
from unittest.mock import patch

from django.test.utils import override_settings

from api.models import Provider
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportManifest

logging.disable(logging.NOTSET)


class TestParquetPostWriteDedup(MasuTestCase):
    """Test _deduplicate_after_write on ParquetReportProcessor."""

    def setUp(self):
        super().setUp()
        self.detect_patcher = patch(
            "masu.processor.parquet.parquet_report_processor.ocp_detect_type",
            return_value=("pod_usage", None),
        )
        self.detect_patcher.start()
        self.addCleanup(self.detect_patcher.stop)
        self.manifest_id = CostUsageReportManifest.objects.filter(cluster_id__isnull=False).first().id
        self.report_name = Path("koku-1.csv.gz")
        self.report_path = f"/my/assembly/{self.report_name}"
        self.ocp_files = {
            "pod_usage.2026-01-15.42.0": {
                "meta_reportdatestart": "2026-01-15",
                "meta_reportnumhours": "24",
            },
        }
        self.processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.ocp_provider_uuid,
            provider_type=Provider.PROVIDER_OCP,
            manifest_id=self.manifest_id,
            context={
                "tracing_id": "test-trace",
                "start_date": self.dh.today,
                "create_table": True,
                "ocp_files_to_process": self.ocp_files,
            },
        )

    @patch(
        "masu.processor.parquet.parquet_report_processor.deduplicate_s3_objects_by_metadata",
        return_value=[],
    )
    @patch("masu.processor.parquet.parquet_report_processor.delete_s3_objects")
    def test_dedup_calls_with_correct_args(self, mock_delete, mock_dedup):
        """Verify the dedup utility is called with expected args from processor state."""
        filename = Path("pod_usage.2026-01-15.42.0.csv")
        self.processor._deduplicate_after_write(filename)

        mock_dedup.assert_called_once_with(
            request_id="test-trace",
            s3_paths=[
                self.processor.parquet_path_s3,
                self.processor.parquet_daily_path_s3,
                self.processor.parquet_ocp_on_cloud_path_s3,
            ],
            current_manifest_id=str(self.manifest_id),
            current_reportnumhours="24",
            reportdatestart="2026-01-15",
            context=self.processor.error_context,
        )
        mock_delete.assert_not_called()

    @patch(
        "masu.processor.parquet.parquet_report_processor.deduplicate_s3_objects_by_metadata",
        return_value=["superseded_file_1.parquet", "superseded_file_2.parquet"],
    )
    @patch("masu.processor.parquet.parquet_report_processor.delete_s3_objects")
    def test_dedup_triggers_deletion_when_duplicates_found(self, mock_delete, mock_dedup):
        """When duplicates are found, their keys are passed to delete_s3_objects."""
        filename = Path("pod_usage.2026-01-15.42.0.csv")
        self.processor._deduplicate_after_write(filename)

        mock_delete.assert_called_once_with(
            "test-trace",
            ["superseded_file_1.parquet", "superseded_file_2.parquet"],
            self.processor.error_context,
        )

    @patch("masu.processor.parquet.parquet_report_processor.deduplicate_s3_objects_by_metadata")
    @patch("masu.processor.parquet.parquet_report_processor.delete_s3_objects")
    def test_dedup_skips_on_missing_metadata(self, mock_delete, mock_dedup):
        """Dedup is skipped when file metadata is missing or incomplete."""
        skip_cases = [
            {
                "label": "file not in ocp_files_to_process",
                "filename": Path("unknown_report.2026-01-15.99.0.csv"),
            },
            {
                "label": "has hours but no reportdatestart",
                "filename": Path("incomplete.2026-01-15.42.0.csv"),
                "extra_files": {
                    "incomplete.2026-01-15.42.0": {"meta_reportnumhours": "24"},
                },
            },
        ]
        for case in skip_cases:
            with self.subTest(case["label"]):
                if extra := case.get("extra_files"):
                    self.processor._context["ocp_files_to_process"].update(extra)
                self.processor._deduplicate_after_write(case["filename"])
                mock_dedup.assert_not_called()
                mock_delete.assert_not_called()


class TestConvertToParquetDedupHook(MasuTestCase):
    """Test that convert_to_parquet calls _deduplicate_after_write correctly."""

    def setUp(self):
        super().setUp()
        self.detect_patcher = patch(
            "masu.processor.parquet.parquet_report_processor.ocp_detect_type",
            return_value=("pod_usage", None),
        )
        self.detect_patcher.start()
        self.addCleanup(self.detect_patcher.stop)
        self.manifest_id = CostUsageReportManifest.objects.filter(cluster_id__isnull=False).first().id
        self.report_name = Path("koku-1.csv.gz")
        self.report_path = f"/my/assembly/{self.report_name}"
        self.ocp_files = {
            "pod_usage.2026-01-15.42.0": {
                "meta_reportdatestart": "2026-01-15",
                "meta_reportnumhours": "24",
            },
        }

    def _make_processor(self, provider_uuid, provider_type, manifest_id=None, extra_context=None):
        context = {
            "tracing_id": "test-trace",
            "start_date": self.dh.today,
            "create_table": True,
            "ocp_files_to_process": self.ocp_files,
            "split_files": [Path("/tmp/pod_usage.2026-01-15.42.0.csv")],
        }
        if extra_context:
            context.update(extra_context)
        return ParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=provider_uuid,
            provider_type=provider_type,
            manifest_id=manifest_id or self.manifest_id,
            context=context,
        )

    @patch("masu.processor.parquet.parquet_report_processor.ParquetReportProcessor._delete_old_data")
    @patch("masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.create_daily_parquet")
    @patch("masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_csv_to_parquet")
    @patch("masu.processor.parquet.parquet_report_processor.ParquetReportProcessor._deduplicate_after_write")
    def test_hook_scenarios(self, mock_dedup, mock_convert, *args):
        """Test that the dedup hook fires for OCP and not for other providers."""
        mock_convert.return_value = ("base", ["col1"], [], True)
        aws_manifest_id = CostUsageReportManifest.objects.filter(cluster_id__isnull=True).first().id

        test_matrix = [
            {
                "label": "OCP SaaS calls dedup",
                "provider_uuid": self.ocp_provider_uuid,
                "provider_type": Provider.PROVIDER_OCP,
                "onprem": False,
                "expect_called": True,
            },
            {
                "label": "OCP on-prem calls dedup (no-op, no S3 parquet files exist)",
                "provider_uuid": self.ocp_provider_uuid,
                "provider_type": Provider.PROVIDER_OCP,
                "onprem": True,
                "expect_called": True,
            },
            {
                "label": "AWS SaaS skips dedup",
                "provider_uuid": self.aws_provider_uuid,
                "provider_type": Provider.PROVIDER_AWS_LOCAL,
                "manifest_id": aws_manifest_id,
                "onprem": False,
                "expect_called": False,
                "extra_context": {
                    "ocp_files_to_process": None,
                    "split_files": [Path("/tmp/some_file.csv")],
                },
            },
        ]
        for scenario in test_matrix:
            with (
                self.subTest(scenario["label"]),
                override_settings(ONPREM=scenario["onprem"]),
            ):
                mock_dedup.reset_mock()
                processor = self._make_processor(
                    scenario["provider_uuid"],
                    scenario["provider_type"],
                    manifest_id=scenario.get("manifest_id"),
                    extra_context=scenario.get("extra_context"),
                )
                processor.convert_to_parquet()
                if scenario["expect_called"]:
                    mock_dedup.assert_called_once()
                else:
                    mock_dedup.assert_not_called()
