"""Masu Azure post processor module tests."""
#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import copy
from unittest.mock import patch

from numpy import isnan
from pandas import DataFrame
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.test import MasuTestCase
from masu.util.azure.azure_post_processor import AzurePostProcessor
from reporting.provider.azure.models import AzureEnabledTagKeys
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

    def test_finalize_post_processing(self):
        """Test that the finalize post processing functionality works.

        Note: For this test we want to process multiple dataframes
        and make sure all keys are found in the db after finalization.
        """
        expected_tag_keys = []
        for idx in range(2):
            expected_tag_key = f"tag_key{idx}"
            expected_tag_keys.append(expected_tag_key)
            tags = str({expected_tag_key: f"val{idx}"}).replace("'", '"')
            data = {"MeterSubCategory": [1], "tags": [tags]}
            data_frame = DataFrame.from_dict(data)
            with patch("masu.util.azure.azure_post_processor.AzurePostProcessor._generate_daily_data"):
                self.post_processor.process_dataframe(data_frame)
                self.assertIn(expected_tag_key, self.post_processor.enabled_tag_keys)
        self.assertEqual(set(expected_tag_keys), self.post_processor.enabled_tag_keys)
        self.post_processor.finalize_post_processing()

        with schema_context(self.schema):
            tag_key_count = AzureEnabledTagKeys.objects.filter(key__in=expected_tag_keys).count()
            self.assertEqual(tag_key_count, len(expected_tag_keys))

    def test_ingress_required_columns(self):
        """Test the ingress required columns."""
        ingress_required_columns = list(copy.deepcopy(self.post_processor.INGRESS_REQUIRED_COLUMNS))
        self.assertIsNone(self.post_processor.check_ingress_required_columns(ingress_required_columns))
        expected_missing_column = ingress_required_columns[-1]
        missing_column = self.post_processor.check_ingress_required_columns(set(ingress_required_columns[:-1]))
        self.assertEqual(missing_column, [expected_missing_column])

    def test_process_json_converter_expected_errors(self):
        """Test process_openshift_datetime method with good and bad values."""
        post_processor = AzurePostProcessor(self.schema)
        csv_converters, panda_kwargs = post_processor.get_column_converters(["tags"], {})
        self.assertEqual({}, panda_kwargs)
        json_converter = csv_converters.get("tags")

        for error in [TypeError, ValueError]:
            with patch("masu.util.ocp.ocp_post_processor.json.loads") as mock_error:
                mock_error.side_effect = error
                dt = json_converter("error")
                self.assertEqual("{}", dt)
