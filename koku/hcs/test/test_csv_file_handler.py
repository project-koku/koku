#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test HCS csv_file_handler."""
from unittest.mock import patch

from dateutil import parser

from api.models import Provider
from api.utils import DateHelper
from hcs.csv_file_handler import CSVFileHandler
from hcs.test import HCSTestCase


class TestHCSCSVFileHandler(HCSTestCase):
    """Test cases for HCS CSV File Handler"""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.provider = Provider.PROVIDER_AWS
        cls.provider_uuid = "cabfdddb-4ed5-421e-a041-311b75daf235"

    def test_init(self):
        """Test the initializer."""
        fh = CSVFileHandler(self.schema, self.provider, self.provider_uuid)
        self.assertEqual(fh._schema_name, "org1234567")
        self.assertEqual(fh._provider, "AWS")
        self.assertEqual(fh._provider_uuid, "cabfdddb-4ed5-421e-a041-311b75daf235")

    @patch("masu.util.aws.common.get_s3_resource")
    def test_write_df_to_csv(self, *args):
        data = {"x": "123", "y": "456", "z": "456"}
        with self.assertLogs("hcs.csv_file_handler", "INFO") as _logs:
            fh = CSVFileHandler(self.schema, self.provider, self.provider_uuid)
            fh.write_csv_to_s3(parser.parse("2022-04-04"), data.items(), "1234-1234-1234")

            self.assertIn("preparing to write file to object storage", _logs.output[0])

    @patch("subs.subs_data_messenger.os.remove")
    @patch("pandas.DataFrame")
    @patch("hcs.csv_file_handler.copy_local_hcs_report_file_to_s3_bucket")
    def test_write_csv_to_s3_finalize(self, mock_copy, mock_df, mock_remove):
        """Test the right finalized date is determine when finalizing a report"""
        data = {"x": "123", "y": "456", "z": "456"}
        date = "2023-08-01"
        datetime_date = parser.parse(date).date()
        year = "2023"
        month = "08"
        expected_filename = f"hcs_{date}.csv"
        mock_trace = "fake_id"
        finalize = True
        expected_finalize_date = "2023-09-15"
        mock_context = {
            "provider_uuid": self.provider_uuid,
            "provider_type": self.provider,
            "schema": self.schema,
            "date": datetime_date,
        }
        expected_s3_path = (
            f"hcs/csv/{self.schema}/{self.provider}/source={self.provider_uuid}/year={year}/month={month}"
        )
        fh = CSVFileHandler(self.schema, self.provider, self.provider_uuid)
        fh.write_csv_to_s3(datetime_date, data.items(), ["x", "y", "z"], finalize, mock_trace)
        mock_copy.assert_called_once_with(
            mock_trace,
            expected_s3_path,
            expected_filename,
            expected_filename,
            finalize,
            expected_finalize_date,
            mock_context,
        )
