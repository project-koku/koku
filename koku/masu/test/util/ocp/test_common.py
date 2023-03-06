#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP util."""
import copy
import datetime
import json
import os
import random
import shutil
import tempfile
from unittest.mock import patch
from uuid import UUID

import pandas as pd

from api.provider.models import Provider
from masu.config import Config
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.test import MasuTestCase
from masu.util.ocp import common as utils


class OCPUtilTests(MasuTestCase):
    """Test the OCP utility functions."""

    def setUp(self):
        """Shared variables used by ocp common tests."""
        super().setUp()
        self.accessor = OCPReportDBAccessor(schema=self.schema)
        self.provider_accessor = ProviderDBAccessor(provider_uuid=self.ocp_test_provider_uuid)
        self.report_schema = self.accessor.report_schema
        self.all_tables = list(OCP_REPORT_TABLE_MAP.values())
        self.provider_uuid = self.provider_accessor.get_provider().uuid

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

    def test_get_provider_uuid_from_cluster_id(self):
        """Test that the provider uuid is returned for a cluster ID."""
        cluster_id = self.ocp_cluster_id
        provider_uuid = utils.get_provider_uuid_from_cluster_id(cluster_id)
        try:
            UUID(provider_uuid)
        except ValueError:
            self.fail(f"{str(provider_uuid)} is not a valid uuid.")

    def test_get_provider_uuid_from_invalid_cluster_id(self):
        """Test that the provider uuid is not returned for an invalid cluster ID."""
        cluster_id = "bad_cluster_id"
        provider_uuid = utils.get_provider_uuid_from_cluster_id(cluster_id)
        self.assertIsNone(provider_uuid)

    def test_poll_ingest_override_for_provider(self):
        """Test that OCP polling override returns True if insights local path exists."""
        fake_dir = tempfile.mkdtemp()
        with patch.object(Config, "INSIGHTS_LOCAL_REPORT_DIR", fake_dir):
            cluster_id = utils.get_cluster_id_from_provider(self.ocp_test_provider_uuid)
            expected_path = f"{Config.INSIGHTS_LOCAL_REPORT_DIR}/{cluster_id}/"
            os.makedirs(expected_path, exist_ok=True)
            self.assertTrue(utils.poll_ingest_override_for_provider(self.ocp_test_provider_uuid))
        shutil.rmtree(fake_dir)

    def test_process_openshift_datetime(self):
        """Test process_openshift_datetime method with good and bad values."""
        expected_dt_str = "2020-07-01 00:00:00"
        expected = pd.to_datetime(expected_dt_str)
        dt = utils.process_openshift_datetime("2020-07-01 00:00:00 +0000 UTC")
        self.assertEqual(expected, dt)

    def test_ocp_generate_daily_data(self):
        """Test that OCP data is aggregated to daily."""
        usage = random.randint(1, 10)
        capacity = random.randint(1, 10)
        namespace = "project_1"
        pod = "pod_1"
        node = "node_1"
        resource_id = "123"
        pvc = "pvc_1"
        label = '{"key": "value"}'

        interval_start = datetime.datetime(2021, 6, 7, 1, 0, 0)
        next_hour = datetime.datetime(2021, 6, 7, 2, 0, 0)
        next_day = datetime.datetime(2021, 6, 8, 1, 0, 0)

        base_data = {
            "report_period_start": datetime.datetime(2021, 6, 1, 0, 0, 0),
            "report_period_end": datetime.datetime(2021, 6, 1, 0, 0, 0),
            "interval_start": interval_start,
            "interval_end": interval_start + datetime.timedelta(hours=1),
        }
        base_next_hour = copy.deepcopy(base_data)
        base_next_hour["interval_start"] = next_hour
        base_next_hour["interval_end"] = next_hour + datetime.timedelta(hours=1)

        base_next_day = copy.deepcopy(base_data)
        base_next_day["interval_start"] = next_day
        base_next_day["interval_end"] = next_day + datetime.timedelta(hours=1)

        base_pod_data = {
            "pod": pod,
            "namespace": namespace,
            "node": node,
            "resource_id": resource_id,
            "pod_usage_cpu_core_seconds": usage,
            "pod_request_cpu_core_seconds": usage,
            "pod_limit_cpu_core_seconds": usage,
            "pod_usage_memory_byte_seconds": usage,
            "pod_request_memory_byte_seconds": usage,
            "pod_limit_memory_byte_seconds": usage,
            "node_capacity_cpu_cores": capacity,
            "node_capacity_cpu_core_seconds": capacity,
            "node_capacity_memory_bytes": capacity,
            "node_capacity_memory_byte_seconds": capacity,
            "pod_labels": label,
        }

        base_storage_data = {
            "namespace": namespace,
            "pod": pod,
            "persistentvolumeclaim": pvc,
            "persistentvolume": pvc,
            "storageclass": "gold",
            "persistentvolumeclaim_capacity_bytes": capacity,
            "persistentvolumeclaim_capacity_byte_seconds": capacity,
            "volume_request_storage_byte_seconds": usage,
            "persistentvolumeclaim_usage_byte_seconds": usage,
            "persistentvolume_labels": label,
            "persistentvolumeclaim_labels": label,
        }

        base_node_data = {"node": node, "node_labels": label}

        base_namespace_data = {"namespace": namespace, "namespace_labels": label}

        base_data_list = [
            ("pod_usage", base_pod_data),
            ("storage_usage", base_storage_data),
            ("node_labels", base_node_data),
            ("namespace_labels", base_namespace_data),
        ]

        for report_type, data in base_data_list:
            data_list = [copy.deepcopy(base_data), copy.deepcopy(base_next_hour), copy.deepcopy(base_next_day)]
            for entry in data_list:
                entry.update(data)
            df = pd.DataFrame(data_list)
            daily_df = utils.ocp_generate_daily_data(df, report_type)

            first_day = daily_df[daily_df["interval_start"] == str(interval_start.date())]
            second_day = daily_df[daily_df["interval_start"] == str(next_day.date())]

            # Assert that there is only 1 record per day
            self.assertEqual(first_day.shape[0], 1)
            self.assertEqual(second_day.shape[0], 1)

            if report_type == "pod_usage":
                self.assertTrue((first_day["pod_usage_cpu_core_seconds"] == usage * 2).bool())
                self.assertTrue((first_day["pod_usage_memory_byte_seconds"] == usage * 2).bool())
                self.assertTrue((first_day["node_capacity_cpu_cores"] == capacity).bool())

                self.assertTrue((second_day["pod_usage_cpu_core_seconds"] == usage).bool())
                self.assertTrue((second_day["pod_usage_memory_byte_seconds"] == usage).bool())
                self.assertTrue((second_day["node_capacity_cpu_cores"] == capacity).bool())
            elif report_type == "storage_usage":
                self.assertTrue((first_day["persistentvolumeclaim_usage_byte_seconds"] == usage * 2).bool())
                self.assertTrue((first_day["volume_request_storage_byte_seconds"] == usage * 2).bool())
                self.assertTrue((first_day["persistentvolumeclaim_capacity_byte_seconds"] == capacity * 2).bool())
                self.assertTrue((first_day["persistentvolumeclaim_capacity_bytes"] == capacity).bool())

                self.assertTrue((second_day["persistentvolumeclaim_usage_byte_seconds"] == usage).bool())
                self.assertTrue((second_day["volume_request_storage_byte_seconds"] == usage).bool())
                self.assertTrue((second_day["persistentvolumeclaim_capacity_byte_seconds"] == capacity).bool())
                self.assertTrue((second_day["persistentvolumeclaim_capacity_bytes"] == capacity).bool())
            elif report_type == "node_labels":
                self.assertTrue((first_day["node"] == node).bool())
                self.assertTrue((first_day["node_labels"] == label).bool())

                self.assertTrue((second_day["node"] == node).bool())
                self.assertTrue((second_day["node_labels"] == label).bool())
            elif report_type == "namespace_labels":
                self.assertTrue((first_day["namespace"] == namespace).bool())
                self.assertTrue((first_day["namespace_labels"] == label).bool())

                self.assertTrue((second_day["namespace"] == namespace).bool())
                self.assertTrue((second_day["namespace_labels"] == label).bool())

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

    def test_get_report_details(self):
        """Test that we handle manifest files properly."""
        with tempfile.TemporaryDirectory() as manifest_path:
            manifest_file = f"{manifest_path}/manifest.json"
            with self.assertLogs("masu.util.ocp.common", level="INFO") as logger:
                expected = f"INFO:masu.util.ocp.common:No manifest available at {manifest_file}"
                utils.get_report_details(manifest_path)
                self.assertIn(expected, logger.output)

            with open(manifest_file, "w") as f:
                data = {"key": "value"}
                json.dump(data, f)
            utils.get_report_details(manifest_path)

            with patch("masu.util.ocp.common.open") as mock_open:
                mock_open.side_effect = OSError
                with self.assertLogs("masu.util.ocp.common", level="INFO") as logger:
                    expected = "ERROR:masu.util.ocp.common:Unable to extract manifest data"
                    utils.get_report_details(manifest_path)
                    self.assertIn(expected, logger.output[0])

    def test_detect_type_pod_usage(self):
        "Test that we detect the correct report type from csv"
        expected_result = "pod_usage"
        test_table = [
            copy.deepcopy(utils.CPU_MEM_USAGE_COLUMNS),
            copy.deepcopy(utils.CPU_MEM_USAGE_COLUMNS).union(utils.CPU_MEM_USAGE_NEWV_COLUMNS),
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
            "storage_usage": copy.deepcopy(utils.STORAGE_COLUMNS),
            "node_labels": copy.deepcopy(utils.NODE_LABEL_COLUMNS),
            "namespace_labels": copy.deepcopy(utils.NAMESPACE_LABEL_COLUMNS),
        }
        for expected, test in test_table.items():
            with self.subTest(test=test):
                with patch("masu.util.ocp.common.pd.read_csv") as mock_csv:
                    mock_csv.return_value.columns = test
                    result, _ = utils.detect_type("")
                    self.assertEqual(result, expected)
