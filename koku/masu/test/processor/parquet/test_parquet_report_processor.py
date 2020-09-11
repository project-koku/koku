#
# Copyright 2020 Red Hat, Inc.
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
import logging
from datetime import timedelta
from unittest.mock import patch

import faker

from api.models import Provider
from api.utils import DateHelper
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.test import MasuTestCase


class TestParquetReportProcessor(MasuTestCase):
    """Test cases for Parquet Report Processor."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.fake = faker.Faker()
        # cls.fake_reports = [
        #     {"file": cls.fake.word(), "compression": "GZIP"},
        #     {"file": cls.fake.word(), "compression": "PLAIN"},
        # ]

        # cls.fake_account = fake_arn(service="iam", generate_account_id=True)
        cls.fake_uuid = "d4703b6e-cd1f-4253-bfd4-32bdeaf24f97"
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)

    def setUp(self):
        """Set up shared test variables."""
        super().setUp()
        self.test_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        self.test_etag = "fake_etag"
        self.report_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=f"/my/{self.test_assembly_id}/koku-1.csv.gz",
            compression="GZIP",
            provider_uuid=self.aws_provider_uuid,
            provider_type=Provider.PROVIDER_AWS_LOCAL,
            manifest_id=1,
            context={"request_id": 1, "start_date": DateHelper().today},
        )

    def test_convert_to_parquet(self):
        """Test the convert_to_parquet task."""
        logging.disable(logging.NOTSET)
        expected_logs = [
            "missing required argument: request_id",
            "missing required argument: account",
            "missing required argument: provider_uuid",
        ]
        with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
            with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
                self.report_processor.convert_to_parquet(None, None, None, None, "start_date", "manifest_id", [])
                for expected in expected_logs:
                    self.assertIn(expected, " ".join(logger.output))

        expected = "Skipping convert_to_parquet. Parquet processing is disabled."
        with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
            self.report_processor.convert_to_parquet(
                "request_id", "account", "provider_uuid", "provider_type", "start_date", "manifest_id", "csv_file"
            )
            self.assertIn(expected, " ".join(logger.output))

        expected = "Parquet processing is enabled, but no start_date was given for processing."
        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
                self.report_processor.convert_to_parquet(
                    "request_id", "account", "provider_uuid", "provider_type", None, "manifest_id", "csv_file"
                )
                self.assertIn(expected, " ".join(logger.output))

        expected = "Parquet processing is enabled, but the start_date was not a valid date string ISO 8601 format."
        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
                self.report_processor.convert_to_parquet(
                    "request_id", "account", "provider_uuid", "provider_type", "bad_date", "manifest_id", "csv_file"
                )
                self.assertIn(expected, " ".join(logger.output))

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix"):
                with patch(
                    "masu.processor.parquet.parquet_report_processor.get_file_keys_from_s3_with_manifest_id",
                    return_value=["cur.csv.gz"],
                ):
                    with patch(
                        "masu.processor.parquet.parquet_report_processor.remove_files_not_in_set_from_s3_bucket"
                    ):
                        with patch("masu.processor.parquet.parquet_report_processor.convert_csv_to_parquet"):
                            self.report_processor.convert_to_parquet(
                                "request_id",
                                "account",
                                "provider_uuid",
                                "AWS",
                                "2020-01-01T12:00:00",
                                "manifest_id",
                                "csv_file",
                            )

        expected = "Failed to convert the following files to parquet"
        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix"):
                with patch(
                    "masu.processor.parquet.parquet_report_processor.get_file_keys_from_s3_with_manifest_id",
                    return_value=["cost_export.csv"],
                ):
                    with patch(
                        "masu.processor.parquet.parquet_report_processor.convert_csv_to_parquet", return_value=False
                    ):
                        with self.assertLogs(
                            "masu.processor.parquet.parquet_report_processor", level="INFO"
                        ) as logger:
                            self.report_processor.convert_to_parquet(
                                "request_id",
                                "account",
                                "provider_uuid",
                                "provider_type",
                                "2020-01-01T12:00:00",
                                "manifest_id",
                                "csv_file",
                            )
                            self.assertIn(expected, " ".join(logger.output))

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix"):
                with patch(
                    "masu.processor.parquet.parquet_report_processor.get_file_keys_from_s3_with_manifest_id",
                    return_value=["storage_usage.csv"],
                ):
                    with patch("masu.processor.parquet.parquet_report_processor.convert_csv_to_parquet"):
                        self.report_processor.convert_to_parquet(
                            "request_id",
                            "account",
                            "provider_uuid",
                            "OCP",
                            "2020-01-01T12:00:00",
                            "manifest_id",
                            "csv_file",
                        )

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix"):
                with patch(
                    "masu.processor.parquet.parquet_report_processor.get_file_keys_from_s3_with_manifest_id",
                    return_value=[],
                ):
                    with patch("masu.processor.parquet.parquet_report_processor.convert_csv_to_parquet"):
                        self.report_processor.convert_to_parquet(
                            "request_id", "account", "provider_uuid", "OCP", "2020-01-01T12:00:00", "manifest_id"
                        )
