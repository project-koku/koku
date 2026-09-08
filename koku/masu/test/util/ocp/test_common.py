#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP util."""
import copy
import json
import tempfile
from unittest.mock import Mock
from unittest.mock import patch

from botocore.exceptions import ClientError
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
        baker.make("Sources", provider=self.ocp_provider, org_id=self.org_id)
        source = utils.get_source_and_provider_from_cluster_id(self.ocp_cluster_id, self.org_id)
        self.assertEqual(source.provider, self.ocp_provider)

    def test_get_source_and_provider_from_cluster_id_invalid_cluster_id(self):
        """Test that the source/provider is not returned for an invalid cluster ID."""
        cluster_id = "bad_cluster_id"
        provider_uuid = utils.get_source_and_provider_from_cluster_id(cluster_id, self.org_id)
        self.assertIsNone(provider_uuid)

    def test_get_source_and_provider_from_cluster_id_cross_org_filter_skipped(self):
        """Test that skip_org_id_filter=True returns a source regardless of org_id mismatch."""
        different_org_id = "different_org"
        baker.make("Sources", provider=self.ocp_provider, org_id=different_org_id)
        # Without skip, a different org_id should return None
        source = utils.get_source_and_provider_from_cluster_id(self.ocp_cluster_id, self.org_id)
        self.assertIsNone(source)
        # With skip, the org_id filter is bypassed and the source is found
        source = utils.get_source_and_provider_from_cluster_id(
            self.ocp_cluster_id, self.org_id, skip_org_id_filter=True
        )
        self.assertIsNotNone(source)
        self.assertEqual(source.provider, self.ocp_provider)

    def test_get_source_and_provider_from_cluster_id_cross_org_filter_enforced(self):
        """Test that skip_org_id_filter=False (default) enforces the org_id filter."""
        baker.make("Sources", provider=self.ocp_provider, org_id=self.org_id)
        wrong_org_id = "wrong_org"
        source = utils.get_source_and_provider_from_cluster_id(
            self.ocp_cluster_id, wrong_org_id, skip_org_id_filter=False
        )
        self.assertIsNone(source)

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

    def test_detect_type_gpu_usage(self):
        """Test that we detect GPU usage report type from csv."""
        expected_result = "gpu_usage"
        test_table = [
            copy.deepcopy(utils.GPU_USAGE_COLUMNS),
            copy.deepcopy(utils.GPU_USAGE_COLUMNS).union(utils.GPU_USAGE_NEWV_COLUMNS_AND_TYPES),
        ]
        for test in test_table:
            with self.subTest(test=test):
                with patch("masu.util.ocp.common.pd.read_csv") as mock_csv:
                    mock_csv.return_value.columns = test
                    result, _ = utils.detect_type("")
                    self.assertEqual(result, expected_result)

    def test_detect_type_gpu_usage_without_mig_columns(self):
        """Test that GPU usage is detected even without MIG columns (backward compatibility)."""
        expected_result = "gpu_usage"
        # Simulate old operator data without MIG columns
        gpu_columns_without_mig = copy.deepcopy(utils.GPU_USAGE_COLUMNS)
        with patch("masu.util.ocp.common.pd.read_csv") as mock_csv:
            mock_csv.return_value.columns = gpu_columns_without_mig
            result, _ = utils.detect_type("")
            self.assertEqual(result, expected_result)

    def test_detect_type_gpu_usage_with_mig_columns(self):
        """Test that GPU usage is detected with MIG columns present."""
        expected_result = "gpu_usage"
        # Simulate new operator data with MIG columns
        gpu_columns_with_mig = copy.deepcopy(utils.GPU_USAGE_COLUMNS).union(
            set(utils.GPU_USAGE_NEWV_COLUMNS_AND_TYPES.keys())
        )
        with patch("masu.util.ocp.common.pd.read_csv") as mock_csv:
            mock_csv.return_value.columns = gpu_columns_with_mig
            result, _ = utils.detect_type("")
            self.assertEqual(result, expected_result)


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

    def test_requires_full_month_field(self):
        """Test requires_full_month field defaults to False and can be set to True."""
        # Test default value is False
        config = utils.DistributionConfig(
            sql_file="test.sql",
            cost_model_rate_type="test",
        )
        self.assertFalse(config.requires_full_month)

        # Test explicit True value
        config = utils.DistributionConfig(
            sql_file="test.sql",
            cost_model_rate_type="test",
            query_type="trino",
            required_table="test_table",
            requires_full_month=True,
        )
        self.assertTrue(config.requires_full_month)

    def test_validate_safe_path_component_rejects_traversal(self):
        """Test path component validation rejects separators and parent references."""
        with self.assertRaises(ValueError):
            utils.validate_safe_path_component("../cluster", "cluster_id")
        with self.assertRaises(ValueError):
            utils.validate_safe_path_component("cluster/nested", "cluster_id")

    def test_manifest_rejects_unsafe_cluster_id_and_file_names(self):
        """Test manifest model rejects unsafe cluster_id and file paths."""
        manifest_data = ManifestFactory.build().model_dump()
        manifest_data["cluster_id"] = "../../evil"
        with self.assertRaises(ValidationError):
            utils.Manifest.model_validate(manifest_data)

        manifest_data = ManifestFactory.build().model_dump()
        manifest_data["files"] = ["../report.csv"]
        with self.assertRaises(ValidationError):
            utils.Manifest.model_validate(manifest_data)

    def test_resolve_path_within_base_rejects_escape(self):
        """Test resolved paths must remain within the base directory."""
        with tempfile.TemporaryDirectory() as base_dir:
            with self.assertRaises(ValueError):
                utils.resolve_path_within_base(base_dir, "..", "escape.txt")


class TestSelectManifestsToDelete(MasuTestCase):
    """Tests for select_manifests_to_delete winner-selection logic."""

    def test_select_manifests_to_delete(self):
        """Test winner selection across multiple scenarios."""
        test_matrix = [
            {
                "label": "empty groups",
                "groups": {},
                "current_id": "100",
                "current_hours": 24,
                "expected": [],
            },
            {
                "label": "single manifest, no conflict",
                "groups": {"100": [{"key": "a.parquet", "reportnumhours": "24"}]},
                "current_id": "100",
                "current_hours": 24,
                "expected": [],
            },
            {
                "label": "current wins with more hours",
                "groups": {
                    "200": [{"key": "ours.parquet", "reportnumhours": "24"}],
                    "100": [{"key": "theirs.parquet", "reportnumhours": "18"}],
                },
                "current_id": "200",
                "current_hours": 24,
                "expected": ["theirs.parquet"],
            },
            {
                "label": "current loses with fewer hours",
                "groups": {
                    "100": [{"key": "ours.parquet", "reportnumhours": "18"}],
                    "200": [{"key": "theirs.parquet", "reportnumhours": "24"}],
                },
                "current_id": "100",
                "current_hours": 18,
                "expected": ["ours.parquet"],
            },
            {
                "label": "equal hours, higher ID wins",
                "groups": {
                    "200": [{"key": "ours.parquet", "reportnumhours": "24"}],
                    "100": [{"key": "theirs.parquet", "reportnumhours": "24"}],
                },
                "current_id": "200",
                "current_hours": 24,
                "expected": ["theirs.parquet"],
            },
            {
                "label": "equal hours, lower ID loses",
                "groups": {
                    "100": [{"key": "ours.parquet", "reportnumhours": "24"}],
                    "200": [{"key": "theirs.parquet", "reportnumhours": "24"}],
                },
                "current_id": "100",
                "current_hours": 24,
                "expected": ["ours.parquet"],
            },
            {
                "label": "multiple files per manifest, superseded manifest fully deleted",
                "groups": {
                    "200": [
                        {"key": "ours_1.parquet", "reportnumhours": "24"},
                        {"key": "ours_2.parquet", "reportnumhours": "24"},
                    ],
                    "100": [
                        {"key": "theirs_1.parquet", "reportnumhours": "18"},
                        {"key": "theirs_2.parquet", "reportnumhours": "18"},
                    ],
                },
                "current_id": "200",
                "current_hours": 24,
                "expected": ["theirs_1.parquet", "theirs_2.parquet"],
            },
            {
                "label": "three manifests, current has middle hours, only deletes own files",
                "groups": {
                    "200": [{"key": "mid.parquet", "reportnumhours": "20"}],
                    "100": [{"key": "low.parquet", "reportnumhours": "18"}],
                    "300": [{"key": "high.parquet", "reportnumhours": "24"}],
                },
                "current_id": "200",
                "current_hours": 20,
                "expected": ["mid.parquet"],
            },
            {
                "label": "three manifests, current is the winner, deletes all others",
                "groups": {
                    "300": [{"key": "ours.parquet", "reportnumhours": "24"}],
                    "200": [{"key": "mid.parquet", "reportnumhours": "20"}],
                    "100": [{"key": "low.parquet", "reportnumhours": "18"}],
                },
                "current_id": "300",
                "current_hours": 24,
                "expected": ["mid.parquet", "low.parquet"],
            },
            {
                "label": "other manifest has None hours, skipped",
                "groups": {
                    "200": [{"key": "ours.parquet", "reportnumhours": "24"}],
                    "100": [{"key": "theirs.parquet", "reportnumhours": None}],
                },
                "current_id": "200",
                "current_hours": 24,
                "expected": [],
            },
        ]
        for scenario in test_matrix:
            with self.subTest(scenario["label"]):
                result = utils.select_manifests_to_delete(
                    scenario["groups"], scenario["current_id"], scenario["current_hours"]
                )
                self.assertCountEqual(result, scenario["expected"])


class TestDeduplicateS3ObjectsByMetadata(MasuTestCase):
    """Tests for deduplicate_s3_objects_by_metadata and _collect_s3_objects_for_day."""

    @staticmethod
    def _make_s3_obj_summary(key, metadata):
        """Helper: create a mock S3 ObjectSummary with .key on summary and .Object() for metadata."""
        obj = Mock(key=key, metadata=metadata)
        summary = Mock(key=key)
        summary.Object.return_value = obj
        return summary

    @patch("masu.util.ocp.common._get_s3_objects")
    def test_dedup_scenarios(self, mock_get):
        """Test dedup across multiple S3 scan scenarios."""
        day = "2026-01-15"
        test_matrix = [
            {
                "label": "single manifest, no duplicates",
                "s3_objects": [
                    self._make_s3_obj_summary(
                        f"pod_usage.{day}.100.0_0.parquet",
                        {"manifestid": "100", "reportnumhours": "24", "reportdatestart": day},
                    ),
                ],
                "current_id": "100",
                "current_hours": "24",
                "expected": [],
            },
            {
                "label": "current wins with more hours",
                "s3_objects": [
                    self._make_s3_obj_summary(
                        f"pod_usage.{day}.200.0_0.parquet",
                        {"manifestid": "200", "reportnumhours": "24", "reportdatestart": day},
                    ),
                    self._make_s3_obj_summary(
                        f"pod_usage.{day}.100.0_0.parquet",
                        {"manifestid": "100", "reportnumhours": "18", "reportdatestart": day},
                    ),
                ],
                "current_id": "200",
                "current_hours": "24",
                "expected": [f"pod_usage.{day}.100.0_0.parquet"],
            },
            {
                "label": "different day filtered out by key pre-check, no conflict",
                "s3_objects": [
                    self._make_s3_obj_summary(
                        f"pod_usage.{day}.200.0_0.parquet",
                        {"manifestid": "200", "reportnumhours": "24", "reportdatestart": day},
                    ),
                    self._make_s3_obj_summary(
                        "pod_usage.2026-01-16.100.0_0.parquet",
                        {"manifestid": "100", "reportnumhours": "18", "reportdatestart": "2026-01-16"},
                    ),
                ],
                "current_id": "200",
                "current_hours": "24",
                "expected": [],
            },
            {
                "label": "missing manifestid ignored, no conflict",
                "s3_objects": [
                    self._make_s3_obj_summary(
                        f"pod_usage.{day}.200.0_0.parquet",
                        {"manifestid": "200", "reportnumhours": "24", "reportdatestart": day},
                    ),
                    self._make_s3_obj_summary(
                        f"pod_usage.{day}.orphan.0_0.parquet",
                        {"reportnumhours": "18", "reportdatestart": day},
                    ),
                ],
                "current_id": "200",
                "current_hours": "24",
                "expected": [],
            },
        ]
        for scenario in test_matrix:
            with self.subTest(scenario["label"]):
                mock_get.return_value = scenario["s3_objects"]
                result = utils.deduplicate_s3_objects_by_metadata(
                    "req",
                    ["path/prefix"],
                    current_manifest_id=scenario["current_id"],
                    current_reportnumhours=scenario["current_hours"],
                    reportdatestart=day,
                )
                self.assertCountEqual(result, scenario["expected"])

    @patch("masu.util.ocp.common._get_s3_objects")
    def test_dedup_aggregates_across_multiple_paths(self, mock_get):
        """Files from hourly, daily, and ocp-on-cloud paths are all scanned for a single day."""
        day = "2026-01-15"
        mock_get.side_effect = [
            [
                self._make_s3_obj_summary(
                    f"hourly/pod_usage.{day}.200.0_0.parquet",
                    {"manifestid": "200", "reportnumhours": "24", "reportdatestart": day},
                )
            ],
            [
                self._make_s3_obj_summary(
                    f"daily/pod_usage.{day}.100.0_daily_0.parquet",
                    {"manifestid": "100", "reportnumhours": "18", "reportdatestart": day},
                )
            ],
            [
                self._make_s3_obj_summary(
                    f"cloud/openshift.{day}.100.0_daily_0.parquet",
                    {"manifestid": "100", "reportnumhours": "18", "reportdatestart": day},
                )
            ],
        ]
        result = utils.deduplicate_s3_objects_by_metadata(
            "req",
            ["path/hourly", "path/daily", "path/cloud"],
            current_manifest_id="200",
            current_reportnumhours="24",
            reportdatestart=day,
        )
        self.assertCountEqual(
            result,
            [f"daily/pod_usage.{day}.100.0_daily_0.parquet", f"cloud/openshift.{day}.100.0_daily_0.parquet"],
        )

    def test_dedup_early_returns(self):
        """Test cases that return early without scanning S3."""
        early_return_cases = [
            {
                "label": "invalid reportnumhours",
                "paths": ["path/prefix"],
                "hours": "invalid",
            },
            {
                "label": "empty string hours",
                "paths": ["path/prefix"],
                "hours": "",
            },
            {
                "label": "None hours",
                "paths": ["path/prefix"],
                "hours": None,
            },
        ]
        for case in early_return_cases:
            with self.subTest(case["label"]):
                result = utils.deduplicate_s3_objects_by_metadata(
                    "req",
                    case["paths"],
                    current_manifest_id="100",
                    current_reportnumhours=case["hours"],
                    reportdatestart="2026-01-15",
                )
                self.assertEqual(result, [])

    @patch("masu.util.ocp.common._get_s3_objects")
    def test_dedup_empty_and_none_paths_skipped(self, mock_get):
        """Empty or None paths are skipped without calling S3."""
        result = utils.deduplicate_s3_objects_by_metadata(
            "req",
            ["", None],
            current_manifest_id="100",
            current_reportnumhours="24",
            reportdatestart="2026-01-15",
        )
        self.assertEqual(result, [])
        mock_get.assert_not_called()

    @patch("masu.util.ocp.common._get_s3_objects", side_effect=ClientError({}, "Error"))
    def test_dedup_s3_error_returns_empty(self, mock_get):
        """S3 errors are caught and return empty list."""
        result = utils.deduplicate_s3_objects_by_metadata(
            "req",
            ["path/prefix"],
            current_manifest_id="100",
            current_reportnumhours="24",
            reportdatestart="2026-01-15",
        )
        self.assertEqual(result, [])
