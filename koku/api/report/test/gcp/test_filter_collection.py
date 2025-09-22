#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test GCP filter collection functions."""
from unittest.mock import patch

from django.test import TestCase

from api.query_filter import QueryFilterCollection
from api.report.gcp.filter_collection import gcp_storage_conditional_filter_collection
from masu.processor import GCP_UNATTRIBUTED_STORAGE_UNLEASH_FLAG


class GCPFilterCollectionTest(TestCase):
    """Tests for GCP filter collection functions."""

    def setUp(self):
        """Set up test data."""
        self.schema_name = "test_schema"

    @patch("api.report.gcp.filter_collection.is_feature_flag_enabled_by_account")
    def test_gcp_storage_conditional_filter_collection_feature_flag_disabled(self, mock_feature_flag):
        """Test GCP storage filter collection when unattributed storage feature flag is disabled."""
        mock_feature_flag.return_value = False
        result = gcp_storage_conditional_filter_collection(self.schema_name)
        mock_feature_flag.assert_called_once_with(self.schema_name, GCP_UNATTRIBUTED_STORAGE_UNLEASH_FLAG)
        self.assertIsNotNone(result)
        expected_services = ["Filestore", "Data Transfer", "Storage", "Cloud Storage"]
        reference_filter = QueryFilterCollection()
        reference_filter.add(field="service_alias", operation="in", parameter=expected_services)
        expected_result = reference_filter.compose()
        self.assertEqual(str(result), str(expected_result))

    @patch("api.report.gcp.filter_collection.is_feature_flag_enabled_by_account")
    def test_gcp_storage_conditional_filter_collection_feature_flag_enabled(self, mock_feature_flag):
        """Test GCP storage filter collection when unattributed storage feature flag is enabled."""
        mock_feature_flag.return_value = True
        result = gcp_storage_conditional_filter_collection(self.schema_name)
        mock_feature_flag.assert_called_once_with(self.schema_name, GCP_UNATTRIBUTED_STORAGE_UNLEASH_FLAG)
        self.assertIsNotNone(result)
        storage_services = QueryFilterCollection()
        storage_services.add(
            field="service_alias", operation="in", parameter=["Filestore", "Data Transfer", "Storage", "Cloud Storage"]
        )

        compute_engine = QueryFilterCollection()
        compute_engine.add(field="service_alias", operation="exact", parameter="Compute Engine")

        sku_alias = QueryFilterCollection()
        sku_alias.add(field="sku_alias", operation="icontains", parameter=" pd ")
        sku_alias.add(field="sku_alias", operation="icontains", parameter=" snapshot ")

        persistent_disk_composed = compute_engine.compose() & sku_alias.compose(logical_operator="or")
        expected_result = storage_services.compose() | persistent_disk_composed
        self.assertEqual(str(result), str(expected_result))

    @patch("api.report.gcp.filter_collection.is_feature_flag_enabled_by_account")
    def test_gcp_storage_conditional_filter_collection_different_schema(self, mock_feature_flag):
        """Test that different schema names are passed correctly to feature flag check."""
        test_schema = "different_test_schema"
        mock_feature_flag.return_value = False
        gcp_storage_conditional_filter_collection(test_schema)
        mock_feature_flag.assert_called_once_with(test_schema, GCP_UNATTRIBUTED_STORAGE_UNLEASH_FLAG)

    def test_gcp_storage_conditional_filter_collection_structure(self):
        """Test that the function returns properly structured filter collections."""
        with patch("api.report.gcp.filter_collection.is_feature_flag_enabled_by_account") as mock_feature_flag:
            for flag_value in [True, False]:
                with self.subTest(feature_flag_enabled=flag_value):
                    mock_feature_flag.return_value = flag_value
                    result = gcp_storage_conditional_filter_collection(self.schema_name)

                    self.assertTrue(hasattr(result, "children"))
                    self.assertTrue(hasattr(result, "connector"))
