"""Masu Azure common module tests."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import numpy as np
import pandas as pd

from masu.test import MasuTestCase
from masu.util.azure.common import match_openshift_resources_and_labels


class TestAzureUtils(MasuTestCase):
    """Tests for Azure utilities."""

    def setUp(self):
        """Set up the test."""
        super().setUp()

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

    def test_match_openshift_resources_and_labels_resource_nan(self):
        """Test that OCP on Azure matching occurs with nan resources."""
        cluster_topology = [
            {
                "resource_ids": [],
                "cluster_id": self.ocp_cluster_id,
                "cluster_alias": "my-ocp-cluster",
                "nodes": ["id1", "id2", "id3"],
                "projects": [],
            }
        ]
        matched_tags = []
        data = [
            {"resourceid": np.nan, "instanceid": "id1", "pretaxcost": 1, "tags": '{"key": "value"}'},
            {"resourceid": np.nan, "instanceid": "id2", "pretaxcost": 1, "tags": '{"key": "other_value"}'},
            {"resourceid": np.nan, "instanceid": "id3", "pretaxcost": 1, "tags": '{"keyz": "value"}'},
        ]

        df = pd.DataFrame(data)
        matched_df = match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["instanceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["instanceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

        result = matched_df[matched_df["instanceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())

    def test_match_openshift_resource_with_nan_labels(self):
        """Test OCP on Azure data matching."""
        cluster_topology = [
            {
                "resource_ids": ["id1", "id2", "id3"],
                "cluster_id": self.ocp_cluster_id,
                "cluster_alias": "my-ocp-cluster",
                "nodes": [],
                "projects": [],
            }
        ]

        matched_tags = [{"key": "value"}]
        data = [
            {"resourceid": "id1", "pretaxcost": 1, "tags": np.nan},
        ]

        df = pd.DataFrame(data)
        matched_df = match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.bool())
