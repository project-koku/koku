"""Masu Azure post processor module tests."""
#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import patch

from numpy import isnan
from pandas import DataFrame

from api.utils import DateHelper
from masu.test import MasuTestCase
from masu.util.azure.azure_post_processor import AzurePostProcessor
from reporting.provider.azure.models import TRINO_COLUMNS


class TestAzurePostProcessor(MasuTestCase):

    """Test Azure Post Processor."""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.post_processor = AzurePostProcessor(self.schema)

    def test_azure_generate_daily_data(self):
        """Test that we return the original data frame."""
        df = DataFrame([{"key": "value"}])
        result = self.post_processor._generate_daily_data(df)
        self.assertEqual(id(df), id(result))

    def test_azure_process_dataframe(self):
        """Test that we end up with a dataframe with the correct columns."""

        data = {"MeterSubCategory": [1], "tags": ['{"key1": "val1", "key2": "val2"}']}
        df = DataFrame(data)

        with patch("masu.util.azure.azure_post_processor.AzurePostProcessor._generate_daily_data"):
            result, _ = self.post_processor.process_dataframe(df)
            columns = list(result)
            expected_columns = sorted(
                col.replace("-", "_").replace("/", "_").replace(":", "_").lower() for col in TRINO_COLUMNS
            )
            self.assertEqual(columns, expected_columns)

    def test_azure_date_converter(self):
        """Test that we convert the new Azure date format."""
        today = DateHelper().today
        csv_converters, panda_kwargs = self.post_processor.get_column_converters(["date"], {})
        self.assertEqual(panda_kwargs, {})
        date_converter = csv_converters.get("date")
        for acceptable_format in ["%Y-%m-%d", "%m/%d/%Y"]:
            with self.subTest(acceptable_format=acceptable_format):
                date = today.strftime(acceptable_format)
                self.assertEqual(date_converter(date).date(), today.date())
        self.assertTrue(isnan(date_converter("")))

    def test_azure_json_converter(self):
        """Test that we successfully process both Azure JSON formats."""
        test_matrix = {
            "resource_type": [
                '{  "ResourceType": "Bandwidth",  "DataCenter": "BN3",  "NetworkBucket": "BY1"}',
                '{"ResourceType": "Bandwidth", "DataCenter": "BN3", "NetworkBucket": "BY1"}',
            ],
            "project": ['{"project":"p1","cost":"management"}', '{"project": "p1", "cost": "management"}'],
            "created-by": [
                '"created-by": "kubernetes-azure","kubernetes.io-created-for-pv-name": "pvc-123"',
                '{"created-by": "kubernetes-azure", "kubernetes.io-created-for-pv-name": "pvc-123"}',
            ],
        }
        csv_converters, panda_kwargs = self.post_processor.get_column_converters(["tags"], {})
        self.assertEqual(panda_kwargs, {})
        json_converter = csv_converters.get("tags")
        for key in test_matrix.keys():
            with self.subTest(key=key):
                unconverted, expected = test_matrix[key]
                self.assertEqual(json_converter(unconverted), expected)
