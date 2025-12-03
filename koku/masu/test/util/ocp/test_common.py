#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP util."""
import copy
import json
import tempfile
from unittest.mock import patch

from model_bakery import baker
from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import ValidationError

from api.provider.models import Provider
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.test import MasuTestCase
from masu.util.ocp import common as utils


class ManifestFactory(ModelFactory[utils.Manifest]):
    ...


class OCPUtilTests(MasuTestCase):
    """Test the OCP utility functions."""

    def setUp(self):
        """Shared variables used by ocp common tests."""
        super().setUp()
        self.accessor = OCPReportDBAccessor(schema=self.schema)
        self.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def test_get_cluster_id_from_provider(self):
        """Test that the cluster ID is returned from OCP provider."""
        cluster_id = utils.get_cluster_id_from_provider(self.ocp_test_provider_uuid)
        self.assertIsNotNone(cluster_id)

    def test_get_cluster_id_with_no_authentication(self):
        """Test that a None is correctly returned if authentication is not present."""
        # Remove test provider authentication
        Provider.objects.filter(uuid=self.ocp_test_provider_uuid).update(authentication=None)
        ocp_provider = Provider.objects.get(uuid=self.ocp_test_provider_uuid)
        self.assertIsNone(ocp_provider.authentication)
        # Assert if authentication is empty we return none instead of an error
        cluster_id = utils.get_cluster_id_from_provider(self.ocp_test_provider_uuid)
        self.assertIsNone(cluster_id)

    def test_get_cluster_id_from_non_ocp_provider(self):
        """Test that None is returned when getting cluster ID on non-OCP provider."""
        cluster_id = utils.get_cluster_id_from_provider(self.aws_provider_uuid)
        self.assertIsNone(cluster_id)

    def test_get_cluster_alias_from_cluster_id(self):
        """Test that the cluster alias is returned from cluster_id."""
        cluster_id = self.ocp_cluster_id
        cluster_alias = utils.get_cluster_alias_from_cluster_id(cluster_id)
        self.assertIsNotNone(cluster_alias)

    def test_get_cluster_alias_from_cluster_id_non_existent_cluster_id(self):
        """Test that the cluster alias is returned from cluster_id."""
        cluster_id = "not a real cluster id"
        cluster_alias = utils.get_cluster_alias_from_cluster_id(cluster_id)
        self.assertIsNone(cluster_alias)

    def test_get_source_and_provider_from_cluster_id(self):
        """Test that the source/provider is returned for a cluster ID."""
        baker.make("Sources", provider=self.ocp_provider)
        cluster_id = self.ocp_cluster_id
        source = utils.get_source_and_provider_from_cluster_id(cluster_id)
        self.assertEqual(source.provider, self.ocp_provider)

    def test_get_source_and_provider_from_cluster_id_invalid_cluster_id(self):
        """Test that the source/provider is not returned for an invalid cluster ID."""
        cluster_id = "bad_cluster_id"
        provider_uuid = utils.get_source_and_provider_from_cluster_id(cluster_id)
        self.assertIsNone(provider_uuid)

    def test_match_openshift_labels(self):
        """Test that a label match returns."""
        matched_tags = [{"key": "value"}, {"other_key": "other_value"}]

        tag_dicts = [
            {"tag": json.dumps({"key": "value"}), "expected": '"key": "value"'},
            {"tag": json.dumps({"key": "other_value"}), "expected": ""},
            {
                "tag": json.dumps({"key": "value", "other_key": "other_value"}),
                "expected": '"key": "value","other_key": "other_value"',
            },
        ]

        for tag_dict in tag_dicts:
            td = tag_dict.get("tag")
            expected = tag_dict.get("expected")
            result = utils.match_openshift_labels(td, matched_tags)
            self.assertEqual(result, expected)

    def test_match_openshift_labels_null_value(self):
        """Test that a label match doesn't return null tag values."""
        matched_tags = [{"key": "value"}, {"other_key": "other_value"}]

        tag_dicts = [
            {"tag": json.dumps({"key": "value"}), "expected": '"key": "value"'},
            {"tag": json.dumps({"key": "other_value"}), "expected": ""},
            {
                "tag": json.dumps({"key": "value", "other_key": "other_value"}),
                "expected": '"key": "value","other_key": "other_value"',
            },
            {"tag": json.dumps({"key": "value", "other_key": None}), "expected": '"key": "value"'},
        ]

        for tag_dict in tag_dicts:
            td = tag_dict.get("tag")
            expected = tag_dict.get("expected")
            result = utils.match_openshift_labels(td, matched_tags)
            self.assertEqual(result, expected)

    def test_parse_manifest(self):
        """Test that we handle manifest files properly."""
        with tempfile.TemporaryDirectory() as manifest_path:
            manifest_file = f"{manifest_path}/manifest.json"
            with open(manifest_file, "w") as f:
                data = {"key": "value"}
                json.dump(data, f)
            with self.assertLogs("masu.util.ocp.common", level="INFO") as logger:
                expected = "unable to extract manifest data"
                with self.assertRaises(ValidationError):
                    utils.parse_manifest(manifest_path)
                self.assertIn(expected, logger.output[0])

    def test_detect_type_pod_usage(self):
        "Test that we detect the correct report type from csv"
        expected_result = "pod_usage"
        test_table = [
            copy.deepcopy(utils.CPU_MEM_USAGE_COLUMNS),
            copy.deepcopy(utils.CPU_MEM_USAGE_COLUMNS).union(utils.CPU_MEM_USAGE_NEWV_COLUMNS_AND_TYPES),
        ]
        for test in test_table:
            with self.subTest(test=test):
                with patch("masu.util.ocp.common.pd.read_csv") as mock_csv:
                    mock_csv.return_value.columns = test
                    result, _ = utils.detect_type("")
                    self.assertEqual(result, expected_result)

    def test_detect_type_storage_type(self):
        "Test that we detect the correct report type from csv"
        expected_result = "storage_usage"
        test_table = [
            copy.deepcopy(utils.STORAGE_COLUMNS),
            copy.deepcopy(utils.STORAGE_COLUMNS).union(utils.STORAGE_NEWV_COLUMNS_AND_TYPES),
        ]
        for test in test_table:
            with self.subTest(test=test):
                with patch("masu.util.ocp.common.pd.read_csv") as mock_csv:
                    mock_csv.return_value.columns = test
                    result, _ = utils.detect_type("")
                    self.assertEqual(result, expected_result)

    def test_detect_type(self):
        "Test that we detect the correct report type from csv"
        test_table = {
            "node_labels": copy.deepcopy(utils.NODE_LABEL_COLUMNS),
            "namespace_labels": copy.deepcopy(utils.NAMESPACE_LABEL_COLUMNS),
        }
        for expected, test in test_table.items():
            with self.subTest(test=test):
                with patch("masu.util.ocp.common.pd.read_csv") as mock_csv:
                    mock_csv.return_value.columns = test
                    result, _ = utils.detect_type("")
                    self.assertEqual(result, expected)


class DistributionConfigTest(MasuTestCase):
    """Test the DistributionConfig class (AI generated tests)."""

    def test_is_trino(self):
        """Test is_trino property."""
        config = utils.DistributionConfig(
            sql_file="test.sql", cost_model_rate_type="test", query_type="trino", required_table="test_table"
        )
        self.assertTrue(config.is_trino)
        self.assertFalse(config.is_postgresql)

    def test_is_postgresql(self):
        """Test is_postgresql property."""
        config = utils.DistributionConfig(
            sql_file="test.sql",
            cost_model_rate_type="test",
            query_type="postgresql",
        )
        self.assertTrue(config.is_postgresql)
        self.assertFalse(config.is_trino)

    def test_has_table_requirement(self):
        """Test has_table_requirement property."""
        config = utils.DistributionConfig(
            sql_file="test.sql", cost_model_rate_type="test", query_type="trino", required_table="test_table"
        )
        self.assertTrue(config.has_table_requirement)

        config = utils.DistributionConfig(
            sql_file="test.sql",
            cost_model_rate_type="test",
            query_type="trino",
        )
        self.assertFalse(config.has_table_requirement)

    def test_validate_required_table(self):
        """Test validate_required_table validator."""
        with self.assertRaises(ValidationError):
            utils.DistributionConfig(
                sql_file="test.sql", cost_model_rate_type="test", query_type="postgresql", required_table="test_table"
            )

    def test_validate_sql_file(self):
        """Test validate_sql_file validator."""
        with self.assertRaises(ValidationError):
            utils.DistributionConfig(
                sql_file="test.txt",
                cost_model_rate_type="test",
            )

    def test_get_full_path(self):
        """Test get_full_path method."""
        # Test trino path
        config = utils.DistributionConfig(
            sql_file="test.sql", cost_model_rate_type="test", query_type="trino", required_table="test_table"
        )
        self.assertEqual(config.get_full_path(), "trino_sql/openshift/cost_model/distribute_cost/test.sql")

        # Test postgres path
        config = utils.DistributionConfig(
            sql_file="test.sql",
            cost_model_rate_type="test",
            query_type="postgresql",
        )
        self.assertEqual(config.get_full_path(), "sql/openshift/cost_model/distribute_cost/test.sql")

    @patch("masu.util.ocp.common.trino_table_exists")
    def test_table_exists(self, mock_table_exists):
        """Test table_exists method."""
        mock_table_exists.return_value = True
        config = utils.DistributionConfig(
            sql_file="test.sql", cost_model_rate_type="test", query_type="trino", required_table="test_table"
        )
        self.assertTrue(config.table_exists(self.schema))
        mock_table_exists.assert_called_once_with(self.schema, "test_table")

        mock_table_exists.return_value = False
        self.assertFalse(config.table_exists(self.schema))

    @patch("masu.util.ocp.common.trino_table_exists")
    def test_table_exists_no_requirement(self, mock_table_exists):
        """Test table_exists method when no table is required."""
        config = utils.DistributionConfig(
            sql_file="test.sql",
            cost_model_rate_type="test",
            query_type="trino",
        )
        self.assertTrue(config.table_exists(self.schema))
        mock_table_exists.assert_not_called()
