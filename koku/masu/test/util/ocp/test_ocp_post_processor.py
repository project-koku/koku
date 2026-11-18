"""Masu OCP post processor module tests."""
#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import copy
import datetime
import random
from json import loads as json_loads
from unittest.mock import patch

import pandas as pd
from dateutil.parser import ParserError

from masu.test import MasuTestCase
from masu.util.ocp.ocp_post_processor import get_gpu_max_slices
from masu.util.ocp.ocp_post_processor import OCPPostProcessor
from masu.util.ocp.ocp_post_processor import parse_mig_profile


class TestOCPPostProcessor(MasuTestCase):
    """Test OCP Post Processor."""

    def setUp(self):
        """Set up test environment."""
        self.schema = "test_schema"
        self.report_type = "pod_usage"
        self.post_processor = OCPPostProcessor(self.schema, self.report_type)
        self.anomalous_data = [
            # Good data
            {
                "pod_usage_cpu_core_seconds": 100,
                "pod_request_cpu_core_seconds": 200,
                "persistentvolumeclaim_capacity_bytes": 10e9,
            },
            # Bad CPU data
            {
                "pod_usage_cpu_core_seconds": 3.7e21,
                "pod_request_cpu_core_seconds": 200,
                "persistentvolumeclaim_capacity_bytes": 10e9,
            },
            # Bad PVC data
            {
                "pod_usage_cpu_core_seconds": 100,
                "pod_request_cpu_core_seconds": 200,
                "persistentvolumeclaim_capacity_bytes": 3.7e21,
            },
            # Another bad PVC data point in byte-seconds
            {
                "pod_usage_cpu_core_seconds": 100,
                "pod_request_cpu_core_seconds": 200,
                "persistentvolumeclaim_capacity_byte_seconds": 3.7e21,
            },
            # Good data with a different set of columns
            {"pod_limit_cpu_core_seconds": 500, "pod_usage_memory_byte_seconds": 10e9},
            # A row with both good and bad data
            {"pod_limit_cpu_core_seconds": 3.7e21, "pod_usage_memory_byte_seconds": 10e9},
        ]
        self.original_df = pd.DataFrame(self.anomalous_data)

    def test_remove_anomalies_no_anomalies(self):
        """Test that the function does not remove rows when there are no anomalies."""
        safe_data = [
            {
                "pod_usage_cpu_core_seconds": 100,
                "pod_request_cpu_core_seconds": 200,
                "persistentvolumeclaim_capacity_bytes": 10e9,
            },
            {
                "pod_usage_cpu_core_seconds": 1e14,
                "pod_request_cpu_core_seconds": 100,
                "persistentvolumeclaim_capacity_bytes": 1e17,
            },
        ]
        test_df = pd.DataFrame(safe_data)
        cleaned_df = self.post_processor._remove_anomalies(test_df, "filename.csv")
        self.assertEqual(len(cleaned_df), len(test_df))

    def test_remove_anomalies_removes_anomalous_rows(self):
        """Test that the function correctly removes anomalous rows."""
        cleaned_df = self.post_processor._remove_anomalies(self.original_df, "filename.csv")
        self.assertEqual(len(cleaned_df), 2)
        self.assertTrue("pod_usage_cpu_core_seconds" in cleaned_df.columns)
        self.assertFalse(cleaned_df["pod_usage_cpu_core_seconds"].isin([1.1e18]).any())
        self.assertFalse(cleaned_df["persistentvolumeclaim_capacity_bytes"].isin([1.1e18]).any())

    def test_remove_anomalies_empty_dataframe(self):
        """Test that the function works correctly with an empty dataframe."""
        test_df = pd.DataFrame()
        cleaned_df = self.post_processor._remove_anomalies(test_df, "filename.csv")
        self.assertTrue(cleaned_df.empty)

    def test_process_dataframe_removes_anomalies(self):
        """Test that the main process_dataframe method correctly calls the anomaly function."""
        with patch.object(self.post_processor, "_generate_daily_data") as mock_generate_daily_data:
            mock_generate_daily_data.return_value = self.original_df.copy()
            self.post_processor.process_dataframe(self.original_df.copy(), "filename.csv")

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
        csi_driver = "ebs.csi.aws.com"

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
            "node": node,
            "csi_driver": csi_driver,
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
            post_processor = OCPPostProcessor(self.schema, report_type)
            daily_df = post_processor._generate_daily_data(df)

            first_day = daily_df[daily_df["interval_start"] == str(interval_start.date())]
            second_day = daily_df[daily_df["interval_start"] == str(next_day.date())]

            # Assert that there is only 1 record per day
            self.assertEqual(first_day.shape[0], 1)
            self.assertEqual(second_day.shape[0], 1)

            if report_type == "pod_usage":
                self.assertTrue((first_day["pod_usage_cpu_core_seconds"] == usage * 2).any(bool_only=True))
                self.assertTrue((first_day["pod_usage_memory_byte_seconds"] == usage * 2).any(bool_only=True))
                self.assertTrue((first_day["node_capacity_cpu_cores"] == capacity).any(bool_only=True))

                self.assertTrue((second_day["pod_usage_cpu_core_seconds"] == usage).any(bool_only=True))
                self.assertTrue((second_day["pod_usage_memory_byte_seconds"] == usage).any(bool_only=True))
                self.assertTrue((second_day["node_capacity_cpu_cores"] == capacity).any(bool_only=True))

                # assert that the new_required_cols have been added:
                self.assertEqual(first_day["node_role"].dtype, pd.StringDtype(storage="pyarrow"))

            elif report_type == "storage_usage":
                self.assertTrue(
                    (first_day["persistentvolumeclaim_usage_byte_seconds"] == usage * 2).any(bool_only=True)
                )
                self.assertTrue((first_day["volume_request_storage_byte_seconds"] == usage * 2).any(bool_only=True))
                self.assertTrue(
                    (first_day["persistentvolumeclaim_capacity_byte_seconds"] == capacity * 2).any(bool_only=True)
                )
                self.assertTrue((first_day["persistentvolumeclaim_capacity_bytes"] == capacity).any(bool_only=True))

                self.assertTrue((second_day["persistentvolumeclaim_usage_byte_seconds"] == usage).any(bool_only=True))
                self.assertTrue((second_day["volume_request_storage_byte_seconds"] == usage).any(bool_only=True))
                self.assertTrue(
                    (second_day["persistentvolumeclaim_capacity_byte_seconds"] == capacity).any(bool_only=True)
                )
                self.assertTrue((second_day["persistentvolumeclaim_capacity_bytes"] == capacity).any(bool_only=True))

                self.assertTrue((first_day["node"] == node).any(bool_only=True))
                self.assertTrue((first_day["csi_driver"] == csi_driver).any(bool_only=True))
                # assert that the new_required_cols have been added:
                self.assertEqual(first_day["csi_volume_handle"].dtype, pd.StringDtype(storage="pyarrow"))

            elif report_type == "node_labels":
                self.assertTrue((first_day["node"] == node).any(bool_only=True))
                self.assertTrue((first_day["node_labels"] == label).any(bool_only=True))

                self.assertTrue((second_day["node"] == node).any(bool_only=True))
                self.assertTrue((second_day["node_labels"] == label).any(bool_only=True))
            elif report_type == "namespace_labels":
                self.assertTrue((first_day["namespace"] == namespace).any(bool_only=True))
                self.assertTrue((first_day["namespace_labels"] == label).any(bool_only=True))

                self.assertTrue((second_day["namespace"] == namespace).any(bool_only=True))
                self.assertTrue((second_day["namespace_labels"] == label).any(bool_only=True))

    def test_ocp_process_dataframe(self):
        """Test the unique tag key processing for OpenShift."""

        for label_type in (
            "pod_labels",
            "persistentvolume_labels",
            "persistentvolumeclaim_labels",
            "namespace_labels",
            "node_labels",
        ):
            with self.subTest(label_type=label_type):
                data = [
                    {
                        "key_one": "value_one",
                        label_type: '{"application": "cost", "environment": "dev", "fun_times": "always"}',
                    },
                    {
                        "key_one": "value_two",
                        label_type: '{"application": "cost", "environment": "dev", "fun_times": "sometimes"}',
                    },
                    {
                        "key_one": "value_one",
                        label_type: '{"application": "cost", "environment": "dev", "fun_times": "maybe?"}',
                    },
                ]
                expected_keys = ["application", "environment", "fun_times"]
                df = pd.DataFrame(data)
                with patch("masu.util.ocp.ocp_post_processor.OCPPostProcessor._generate_daily_data"):
                    post_processor = OCPPostProcessor(self.schema, "pod_usage")
                    processed_df, _ = post_processor.process_dataframe(df, "filename.csv")
                pd.testing.assert_frame_equal(df, processed_df)
                self.assertEqual(sorted(post_processor.enabled_tag_keys), sorted(expected_keys))

        label_type = "incorrect_labels_column"
        data = [
            {
                "key_one": "value_one",
                label_type: '{"application": "cost", "environment": "dev", "fun_times": "always"}',
            },
            {
                "key_one": "value_two",
                label_type: '{"application": "cost", "environment": "dev", "fun_times": "sometimes"}',
            },
            {
                "key_one": "value_one",
                label_type: '{"application": "cost", "environment": "dev", "fun_times": "maybe?"}',
            },
        ]
        expected_keys = ["application", "environment", "fun_times"]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "pod_usage")
        with patch("masu.util.ocp.ocp_post_processor.OCPPostProcessor._generate_daily_data"):
            processed_df, _ = post_processor.process_dataframe(df, "filename.csv")
            pd.testing.assert_frame_equal(df, processed_df)
            self.assertEqual(post_processor.enabled_tag_keys, set())

    def test_process_openshift_datetime(self):
        """Test process_openshift_datetime method with good and bad values."""
        post_processor = OCPPostProcessor(self.schema, "pod_usage")
        csv_converters, panda_kwargs = post_processor.get_column_converters(["report_period_start"], {})
        self.assertEqual({}, panda_kwargs)
        datetime_converter = csv_converters.get("report_period_start")
        expected_dt_str = "2020-07-01 00:00:00"
        expected = pd.to_datetime(expected_dt_str)
        dt = datetime_converter("2020-07-01 00:00:00 +0000 UTC")
        self.assertEqual(expected, dt)

    def test_process_openshift_datetime_parse_error(self):
        """Test process_openshift_datetime method with good and bad values."""
        post_processor = OCPPostProcessor(self.schema, "pod_usage")
        csv_converters, panda_kwargs = post_processor.get_column_converters(["report_period_start"], {})
        self.assertEqual({}, panda_kwargs)
        datetime_converter = csv_converters.get("report_period_start")
        with patch("masu.util.ocp.ocp_post_processor.ciso8601.parse_datetime") as mock_parse:
            mock_parse.side_effect = ParserError
            dt = datetime_converter("parse error")
            self.assertTrue(pd.isnull(dt))

    def test_check_ingress_required_columns(self):
        """Test that None is returned."""
        post_processor = OCPPostProcessor(self.schema, "pod_usage")
        self.assertIsNone(post_processor.check_ingress_required_columns([]))

    def test_process_openshift_labels(self):
        """Test that labels are correctly processed."""
        converter_column = "pod_labels"
        post_processor = OCPPostProcessor(self.schema, "pod_usage")
        csv_converters, panda_kwargs = post_processor.get_column_converters([converter_column], {})
        self.assertEqual({}, panda_kwargs)
        label_converter = csv_converters.get(converter_column)
        example_label = "label_environment:ruby|label_app:fall|label_version:red"
        result = label_converter(example_label)
        self.assertIsInstance(result, str)
        result = json_loads(result)
        self.assertEqual(result.get("environment"), "ruby")
        self.assertEqual(result.get("app"), "fall")
        self.assertEqual(result.get("version"), "red")

    def test_process_openshift_labels_unexpected_strings(self):
        """Test that unexpected labels return str of empty dict."""
        converter_column = "pod_labels"
        post_processor = OCPPostProcessor(self.schema, "pod_usage")
        csv_converters, panda_kwargs = post_processor.get_column_converters([converter_column], {})
        self.assertEqual({}, panda_kwargs)
        label_converter = csv_converters.get(converter_column)
        unexpected_strings = [
            "label_environment:ruby?label_app:fall?label_version:red",  # no |
            "label_environment?ruby|label_app?fall|label_version?red",  # no :
        ]
        for string in unexpected_strings:
            result = label_converter(string)
            self.assertIsInstance(result, str)
            self.assertEqual(result, "{}")

    def test_gernerate_daily_data_empty_dataframe(self):
        """Test if we pass in an empty dataframe, we get one back."""
        df = pd.DataFrame()
        post_processor = OCPPostProcessor(self.schema, "storage_usage")
        processed_df = post_processor._generate_daily_data(df)
        self.assertTrue(processed_df.empty)

    def test_populate_mig_fields_from_profile(self):
        """Test that MIG fields are populated from profile."""
        data = [
            {
                "node": "gpu-node-1",
                "namespace": "ml-training",
                "pod": "training-pod",
                "gpu_uuid": "GPU-123",
                "gpu_model_name": "A100",
                "gpu_vendor_name": "nvidia",
                "gpu_memory_capacity_mib": 81920,
                "gpu_pod_uptime": 3600,
                "mig_instance_id": "MIG-456",
                "mig_profile": "4g.40gb",
            },
            {
                "node": "gpu-node-1",
                "namespace": "inference",
                "pod": "inference-pod",
                "gpu_uuid": "GPU-123",
                "gpu_model_name": "A100",
                "gpu_vendor_name": "nvidia",
                "gpu_memory_capacity_mib": 81920,
                "gpu_pod_uptime": 7200,
                "mig_instance_id": "MIG-789",
                "mig_profile": "1g.10gb",
            },
        ]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "gpu_usage")
        processed_df = post_processor._populate_mig_fields_from_profile(df)

        # Check that mig_slice_count was populated from profile
        self.assertEqual(processed_df.at[0, "mig_slice_count"], 4)
        self.assertEqual(processed_df.at[1, "mig_slice_count"], 1)

        # Check that mig_memory_capacity_mib was populated from profile
        self.assertEqual(processed_df.at[0, "mig_memory_capacity_mib"], 40960)
        self.assertEqual(processed_df.at[1, "mig_memory_capacity_mib"], 10240)

        # Check that gpu_max_slices was populated from GPU model
        self.assertEqual(processed_df.at[0, "gpu_max_slices"], 7)
        self.assertEqual(processed_df.at[1, "gpu_max_slices"], 7)

    def test_populate_mig_fields_non_gpu_report(self):
        """Test that MIG field population is skipped for non-GPU reports."""
        data = [{"node": "node-1", "namespace": "default", "pod": "pod-1"}]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "pod_usage")
        processed_df = post_processor._populate_mig_fields_from_profile(df)

        # Should return unchanged dataframe
        pd.testing.assert_frame_equal(df, processed_df)

    def test_populate_mig_fields_no_mig_profile(self):
        """Test that MIG field population is skipped when no mig_profile column exists."""
        data = [
            {
                "node": "gpu-node-1",
                "namespace": "default",
                "pod": "pod-1",
                "gpu_uuid": "GPU-123",
                "gpu_model_name": "Tesla T4",
            }
        ]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "gpu_usage")
        processed_df = post_processor._populate_mig_fields_from_profile(df)

        # Should return unchanged dataframe
        pd.testing.assert_frame_equal(df, processed_df)

    def test_populate_mig_fields_empty_mig_profile(self):
        """Test that MIG field population handles empty mig_profile values."""
        data = [
            {
                "node": "gpu-node-1",
                "namespace": "default",
                "pod": "pod-1",
                "gpu_uuid": "GPU-123",
                "gpu_model_name": "Tesla T4",
                "mig_profile": "",
            },
            {
                "node": "gpu-node-2",
                "namespace": "default",
                "pod": "pod-2",
                "gpu_uuid": "GPU-456",
                "gpu_model_name": "Tesla T4",
                "mig_profile": None,
            },
        ]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "gpu_usage")
        processed_df = post_processor._populate_mig_fields_from_profile(df)

        # Should not add MIG fields for rows without valid mig_profile
        self.assertFalse("mig_slice_count" in processed_df.columns and processed_df["mig_slice_count"].notna().any())

    def test_populate_mig_fields_derives_from_profile(self):
        """Test that MIG fields are derived from the profile."""
        data = [
            {
                "node": "gpu-node-1",
                "namespace": "ml-training",
                "pod": "training-pod",
                "gpu_uuid": "GPU-123",
                "gpu_model_name": "A100",
                "mig_profile": "4g.40gb",
                "mig_slice_count": 4,  # Already set
                "mig_memory_capacity_mib": 40960,  # Already set
                "gpu_max_slices": 7,  # Already set
            },
        ]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "gpu_usage")
        processed_df = post_processor._populate_mig_fields_from_profile(df)

        # Values should be derived from profile "4g.40gb"
        self.assertEqual(processed_df.at[0, "mig_slice_count"], 4)
        self.assertEqual(processed_df.at[0, "mig_memory_capacity_mib"], 40960)
        self.assertEqual(processed_df.at[0, "gpu_max_slices"], 7)


class MIGProfileParsingTest(MasuTestCase):
    """Test the MIG profile parsing utility functions."""

    def test_parse_mig_profile_valid(self):
        """Test parsing valid MIG profiles."""
        test_cases = [
            ("1g.5gb", (1, 5120)),
            ("1g.10gb", (1, 10240)),
            ("2g.10gb", (2, 10240)),
            ("2g.20gb", (2, 20480)),
            ("3g.20gb", (3, 20480)),
            ("3g.40gb", (3, 40960)),
            ("4g.20gb", (4, 20480)),
            ("4g.40gb", (4, 40960)),
            ("7g.40gb", (7, 40960)),
            ("7g.80gb", (7, 81920)),
        ]
        for profile, expected in test_cases:
            with self.subTest(profile=profile):
                result = parse_mig_profile(profile)
                self.assertEqual(result, expected)

    def test_parse_mig_profile_case_insensitive(self):
        """Test that MIG profile parsing is case insensitive."""
        test_cases = [
            ("1G.5GB", (1, 5120)),
            ("1g.5GB", (1, 5120)),
            ("1G.5gb", (1, 5120)),
        ]
        for profile, expected in test_cases:
            with self.subTest(profile=profile):
                result = parse_mig_profile(profile)
                self.assertEqual(result, expected)

    def test_parse_mig_profile_invalid(self):
        """Test parsing invalid MIG profiles returns (None, None)."""
        test_cases = [
            None,
            "",
            "   ",
            "invalid",
            "1g",
            "5gb",
            "1g.5",
            "1.5gb",
            "1g5gb",
        ]
        for profile in test_cases:
            with self.subTest(profile=profile):
                result = parse_mig_profile(profile)
                self.assertEqual(result, (None, None))

    def test_get_gpu_max_slices_known_models(self):
        """Test getting max slices for known GPU models."""
        test_cases = [
            ("A100", 7),
            ("a100", 7),  # Case insensitive
            ("A100-40GB", 7),
            ("A100-80GB", 7),
            ("H100", 7),
            ("H100-80GB", 7),
            ("A30", 4),
        ]
        for model, expected in test_cases:
            with self.subTest(model=model):
                result = get_gpu_max_slices(model)
                self.assertEqual(result, expected)

    def test_get_gpu_max_slices_partial_match(self):
        """Test getting max slices with partial model name match."""
        test_cases = [
            ("NVIDIA A100-80GB-PCIe", 7),
            ("NVIDIA-A100-SXM4", 7),
            ("H100-SXM5-80GB", 7),
        ]
        for model, expected in test_cases:
            with self.subTest(model=model):
                result = get_gpu_max_slices(model)
                self.assertEqual(result, expected)

    def test_get_gpu_max_slices_unknown_model(self):
        """Test getting max slices for unknown GPU model returns None (treat as dedicated)."""
        result = get_gpu_max_slices("UnknownGPU")
        self.assertIsNone(result)

    def test_get_gpu_max_slices_none_model(self):
        """Test getting max slices with None model returns None (treat as dedicated)."""
        result = get_gpu_max_slices(None)
        self.assertIsNone(result)


class TestMIGFieldsForUnknownModels(MasuTestCase):
    """Test that MIG fields are cleared for unknown GPU models."""

    def setUp(self):
        """Set up test environment."""
        self.schema = "test_schema"

    def test_populate_mig_fields_clears_for_unknown_model(self):
        """Test that MIG fields are cleared for unknown GPU models (treated as dedicated)."""
        data = [
            {
                "node": "gpu-node-1",
                "namespace": "ml-training",
                "pod": "training-pod",
                "gpu_uuid": "GPU-123",
                "gpu_model_name": "UnknownGPU",
                "gpu_vendor_name": "nvidia",
                "gpu_memory_capacity_mib": 81920,
                "gpu_pod_uptime": 3600,
                "mig_instance_id": "MIG-456",
                "mig_profile": "4g.40gb",
            },
        ]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "gpu_usage")
        processed_df = post_processor._populate_mig_fields_from_profile(df)

        # Unknown model should have MIG fields cleared and be treated as dedicated
        self.assertTrue(pd.isna(processed_df.at[0, "mig_profile"]))
        self.assertTrue(pd.isna(processed_df.at[0, "mig_slice_count"]))
        self.assertTrue(pd.isna(processed_df.at[0, "gpu_max_slices"]))
        self.assertTrue(pd.isna(processed_df.at[0, "mig_instance_id"]))

    def test_populate_mig_fields_clears_for_unparseable_profile(self):
        """Test that MIG fields are cleared when profile can't be parsed and model is unknown."""
        data = [
            {
                "node": "gpu-node-1",
                "namespace": "ml-training",
                "pod": "training-pod",
                "gpu_uuid": "GPU-123",
                "gpu_model_name": "UnknownGPU",
                "gpu_vendor_name": "nvidia",
                "gpu_memory_capacity_mib": 81920,
                "gpu_pod_uptime": 3600,
                "mig_instance_id": "MIG-456",
                "mig_profile": "invalid-profile",
            },
        ]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "gpu_usage")
        processed_df = post_processor._populate_mig_fields_from_profile(df)

        # Can't parse profile and unknown model, so MIG fields should be cleared
        self.assertTrue(pd.isna(processed_df.at[0, "mig_profile"]))
        self.assertTrue(pd.isna(processed_df.at[0, "mig_slice_count"]))
        self.assertTrue(pd.isna(processed_df.at[0, "gpu_max_slices"]))
        self.assertTrue(pd.isna(processed_df.at[0, "mig_instance_id"]))

    def test_populate_mig_fields_preserves_for_known_model(self):
        """Test that MIG fields are preserved for known GPU models."""
        data = [
            {
                "node": "gpu-node-1",
                "namespace": "ml-training",
                "pod": "training-pod",
                "gpu_uuid": "GPU-123",
                "gpu_model_name": "A100",
                "gpu_vendor_name": "nvidia",
                "gpu_memory_capacity_mib": 81920,
                "gpu_pod_uptime": 3600,
                "mig_instance_id": "MIG-456",
                "mig_profile": "4g.40gb",
            },
        ]
        df = pd.DataFrame(data)
        post_processor = OCPPostProcessor(self.schema, "gpu_usage")
        processed_df = post_processor._populate_mig_fields_from_profile(df)

        # Known model should have MIG fields preserved and max_slices populated
        self.assertEqual(processed_df.at[0, "mig_profile"], "4g.40gb")
        self.assertEqual(processed_df.at[0, "mig_slice_count"], 4)
        self.assertEqual(processed_df.at[0, "mig_memory_capacity_mib"], 40960)
        self.assertEqual(processed_df.at[0, "gpu_max_slices"], 7)
