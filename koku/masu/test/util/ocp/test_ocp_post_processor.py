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
from masu.util.ocp.ocp_post_processor import OCPPostProcessor


class TestOCPPostProcessor(MasuTestCase):
    """Test OCP Post Processor."""

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
            "unexpected_column": None,
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
            "unexpected_column": None,
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
            post_processor = OCPPostProcessor(self.schema_name, report_type)
            daily_df = post_processor._generate_daily_data(df)

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

    def test_ocp_process_dataframe(self):
        """Test the unique tag key processing for OpenShift."""

        for label_type in ("pod_labels", "volume_labels", "namespace_labels", "node_labels"):
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
                    post_processor = OCPPostProcessor(self.schema_name, "pod_usage")
                    processed_df, _ = post_processor.process_dataframe(df)
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
        post_processor = OCPPostProcessor(self.schema_name, "pod_usage")
        with patch("masu.util.ocp.ocp_post_processor.OCPPostProcessor._generate_daily_data"):
            processed_df, _ = post_processor.process_dataframe(df)
            pd.testing.assert_frame_equal(df, processed_df)
            self.assertEqual(post_processor.enabled_tag_keys, set())

    def test_process_openshift_datetime(self):
        """Test process_openshift_datetime method with good and bad values."""
        post_processor = OCPPostProcessor(self.schema_name, "pod_usage")
        csv_converters, panda_kwargs = post_processor.get_column_converters(["report_period_start"], {})
        self.assertEqual({}, panda_kwargs)
        datetime_converter = csv_converters.get("report_period_start")
        expected_dt_str = "2020-07-01 00:00:00"
        expected = pd.to_datetime(expected_dt_str)
        dt = datetime_converter("2020-07-01 00:00:00 +0000 UTC")
        self.assertEqual(expected, dt)

    def test_process_openshift_datetime_parse_error(self):
        """Test process_openshift_datetime method with good and bad values."""
        post_processor = OCPPostProcessor(self.schema_name, "pod_usage")
        csv_converters, panda_kwargs = post_processor.get_column_converters(["report_period_start"], {})
        self.assertEqual({}, panda_kwargs)
        datetime_converter = csv_converters.get("report_period_start")
        with patch("masu.util.ocp.ocp_post_processor.ciso8601.parse_datetime") as mock_parse:
            mock_parse.side_effect = ParserError
            dt = datetime_converter("parse error")
            self.assertIsNone(dt)

    def test_check_ingress_required_columns(self):
        """Test that None is returned."""
        post_processor = OCPPostProcessor(self.schema_name, "pod_usage")
        self.assertIsNone(post_processor.check_ingress_required_columns([]))

    def test_process_openshift_labels(self):
        """Test that labels are correctly processed."""
        converter_column = "pod_labels"
        post_processor = OCPPostProcessor(self.schema_name, "pod_usage")
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
        post_processor = OCPPostProcessor(self.schema_name, "pod_usage")
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
        post_processor = OCPPostProcessor(self.schema_name, "storage_usage")
        processed_df = post_processor._generate_daily_data(df)
        self.assertTrue(processed_df.empty)
