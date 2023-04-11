"""Masu AWS common module tests."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import patch

import numpy as np
import pandas as pd

from api.utils import DateHelper
from masu.test import MasuTestCase
from masu.util.azure.azure_post_processor import AzurePostProcessor
from masu.util.azure.common import match_openshift_resources_and_labels
from reporting.provider.azure.models import TRINO_COLUMNS


class TestAzureUtils(MasuTestCase):
    """Tests for Azure utilities."""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.post_processor = AzurePostProcessor(self.schema)

    def test_match_openshift_resources_and_labels(self):
        """Test that OCP on Azure matching occurs."""
        cluster_topology = [
            {
                "resource_ids": [],
                "cluster_id": self.ocp_cluster_id,
                "cluster_alias": "my-ocp-cluster",
                "nodes": ["id1", "id2", "id3"],
                "projects": [],
            }
        ]

        matched_tags = [{"key": "value"}]

        data = [
            {"resourceid": "id1", "pretaxcost": 1, "tags": '{"key": "value"}'},
            {"resourceid": "id2", "pretaxcost": 1, "tags": '{"key": "other_value"}'},
            {"resourceid": "id4", "pretaxcost": 1, "tags": '{"keyz": "value"}'},
            {"resourceid": "id5", "pretaxcost": 1, "tags": '{"key": "value"}'},
        ]

        df = pd.DataFrame(data)

        matched_df = match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        result = matched_df[matched_df["resourceid"] == "id4"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        # tag matching
        result = matched_df[matched_df["resourceid"] == "id1"]["matched_tag"] == '"key": "value"'
        self.assertTrue(result.bool())

        result = matched_df[matched_df["resourceid"] == "id5"]["matched_tag"] == '"key": "value"'
        self.assertTrue(result.bool())

        # Matched tags, but none that match the dataset
        matched_tags = [{"something_else": "entirely"}]
        matched_df = match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        result = matched_df[matched_df["resourceid"] == "id4"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)
        # tag matching
        self.assertFalse((matched_df["matched_tag"] != "").any())

        # No matched tags
        matched_tags = []
        matched_df = match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        result = matched_df[matched_df["resourceid"] == "id4"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        # tag matching
        self.assertFalse((matched_df["matched_tag"] != "").any())


class TestAzurePostProcessor(MasuTestCase):

    """Test Azure Post Processor."""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.post_processor = AzurePostProcessor(self.schema)

    def test_azure_generate_daily_data(self):
        """Test that we return the original data frame."""
        df = pd.DataFrame([{"key": "value"}])
        result = self.post_processor._generate_daily_data(df)
        self.assertEqual(id(df), id(result))

    def test_azure_post_processor(self):
        """Test that we end up with a dataframe with the correct columns."""

        data = {"MeterSubCategory": [1], "tags": ['{"key1": "val1", "key2": "val2"}']}
        df = pd.DataFrame(data)

        with patch("masu.util.azure.azure_post_processor.AzurePostProcessor._generate_daily_data"):
            result, _ = self.post_processor.process_dataframe(df)
            if isinstance(result, tuple):
                result, df_tag_keys, _ = result
                self.assertIsInstance(df_tag_keys, set)

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
        self.assertTrue(np.isnan(date_converter("")))

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
