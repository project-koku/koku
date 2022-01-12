"""Masu AWS common module tests."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import numpy as np
import pandas as pd

from api.utils import DateHelper
from masu.test import MasuTestCase
from masu.util.azure.common import azure_date_converter
from masu.util.azure.common import azure_generate_daily_data
from masu.util.azure.common import azure_json_converter
from masu.util.azure.common import azure_post_processor
from masu.util.azure.common import match_openshift_resources_and_labels
from reporting.provider.azure.models import PRESTO_COLUMNS


class TestAzureUtils(MasuTestCase):
    """Tests for Azure utilities."""

    def test_azure_date_converter(self):
        """Test that we convert the new Azure date format."""
        today = DateHelper().today
        old_azure_format = today.strftime("%Y-%m-%d")
        new_azure_format = today.strftime("%m/%d/%Y")

        self.assertEqual(azure_date_converter(old_azure_format).date(), today.date())
        self.assertEqual(azure_date_converter(new_azure_format).date(), today.date())
        self.assertTrue(np.isnan(azure_date_converter("")))

    def test_azure_json_converter(self):
        """Test that we successfully process both Azure JSON formats."""

        first_format = '{  "ResourceType": "Bandwidth",  "DataCenter": "BN3",  "NetworkBucket": "BY1"}'
        first_expected = '{"ResourceType": "Bandwidth", "DataCenter": "BN3", "NetworkBucket": "BY1"}'

        self.assertEqual(azure_json_converter(first_format), first_expected)

        second_format = '{"project":"p1","cost":"management"}'
        second_expected = '{"project": "p1", "cost": "management"}'

        self.assertEqual(azure_json_converter(second_format), second_expected)

        third_format = '"created-by": "kubernetes-azure","kubernetes.io-created-for-pv-name": "pvc-123"'
        third_expected = '{"created-by": "kubernetes-azure", "kubernetes.io-created-for-pv-name": "pvc-123"}'

        self.assertEqual(azure_json_converter(third_format), third_expected)

    def test_azure_post_processor(self):
        """Test that we end up with a dataframe with the correct columns."""

        data = {"MeterSubCategory": [1]}
        df = pd.DataFrame(data)
        result = azure_post_processor(df)
        if isinstance(result, tuple):
            result, df_tag_keys = result
            self.assertIsInstance(df_tag_keys, set)

        columns = list(result)

        expected_columns = sorted(
            [col.replace("-", "_").replace("/", "_").replace(":", "_").lower() for col in PRESTO_COLUMNS]
        )

        self.assertEqual(columns, expected_columns)

    def test_azure_generate_daily_data(self):
        """Test that we return the original data frame."""
        df = pd.DataFrame([{"key": "value"}])
        result = azure_generate_daily_data(df)
        self.assertEqual(id(df), id(result))

    def test_match_openshift_resources_and_labels(self):
        """Test that OCP on Azure matching occurs."""
        cluster_topology = {
            "resource_ids": [],
            "cluster_id": self.ocp_cluster_id,
            "cluster_alias": "my-ocp-cluster",
            "nodes": ["id1", "id2", "id3"],
            "projects": [],
        }

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
