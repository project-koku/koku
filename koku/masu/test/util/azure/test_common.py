"""Masu Azure common module tests."""
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import pandas as pd
from django_tenants.utils import schema_context

from masu.test import MasuTestCase
from masu.util.azure import common as utils
from reporting.models import AzureCostEntryBill


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
            {"resourceid": "id1", "costinbillingcurrency": 1, "tags": '{"key": "value"}'},
            {"resourceid": "id2", "costinbillingcurrency": 1, "tags": '{"key": "other_value"}'},
            {"resourceid": "id4", "costinbillingcurrency": 1, "tags": '{"keyz": "value"}'},
            {"resourceid": "id5", "costinbillingcurrency": 1, "tags": '{"key": "value"}'},
        ]

        df = pd.DataFrame(data)

        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

        result = matched_df[matched_df["resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

        result = matched_df[matched_df["resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        result = matched_df[matched_df["resourceid"] == "id4"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        # tag matching
        result = matched_df[matched_df["resourceid"] == "id1"]["matched_tag"] == '"key": "value"'
        self.assertTrue(result.any(bool_only=True))

        result = matched_df[matched_df["resourceid"] == "id5"]["matched_tag"] == '"key": "value"'
        self.assertTrue(result.any(bool_only=True))

        # Matched tags, but none that match the dataset
        matched_tags = [{"something_else": "entirely"}]
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

        result = matched_df[matched_df["resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

        result = matched_df[matched_df["resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)

        result = matched_df[matched_df["resourceid"] == "id4"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.empty)
        # tag matching
        self.assertFalse((matched_df["matched_tag"] != "").any())

        # No matched tags
        matched_tags = []
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

        result = matched_df[matched_df["resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

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
            {"resourceid": "id1", "costinbillingcurrency": 1, "tags": '{"key": "value"}'},
            {"resourceid": "id2", "costinbillingcurrency": 1, "tags": '{"key": "other_value"}'},
            {"resourceid": "id3", "costinbillingcurrency": 1, "tags": '{"keyz": "value"}'},
        ]

        df = pd.DataFrame(data)
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

        result = matched_df[matched_df["resourceid"] == "id2"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

        result = matched_df[matched_df["resourceid"] == "id3"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

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
            {"resourceid": "id1", "costinbillingcurrency": 1, "tags": ""},
        ]

        df = pd.DataFrame(data)
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # resource id matching
        result = matched_df[matched_df["resourceid"] == "id1"]["resource_id_matched"] == True  # noqa: E712
        self.assertTrue(result.any(bool_only=True))

    def test_get_bill_ids_from_provider(self):
        """Test that bill IDs are returned for an AWS provider."""
        with schema_context(self.schema):
            expected_bill_ids = AzureCostEntryBill.objects.values_list("id")
            expected_bill_ids = sorted(bill_id[0] for bill_id in expected_bill_ids)
        bills = utils.get_bills_from_provider(self.azure_provider_uuid, self.schema)

        with schema_context(self.schema):
            bill_ids = sorted(bill.id for bill in bills)

        self.assertEqual(bill_ids, expected_bill_ids)

        # Try with unknown provider uuid
        bills = utils.get_bills_from_provider(self.unkown_test_provider_uuid, self.schema)
        self.assertEqual(bills, [])
