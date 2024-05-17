"""Masu GCP post processor module tests."""
#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import random
from datetime import datetime
from unittest.mock import patch

from django_tenants.utils import schema_context
from pandas import DataFrame

from api.models import Provider
from masu.test import MasuTestCase
from masu.util.gcp.gcp_post_processor import GCPPostProcessor
from masu.util.gcp.gcp_post_processor import process_gcp_credits
from reporting.provider.all.models import EnabledTagKeys


class TestGCPPostProcessor(MasuTestCase):
    """Test GCP Post Processor."""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.post_processor = GCPPostProcessor(self.schema)

    def test_gcp_generate_daily_data(self):
        """Test that we aggregate data at a daily level."""
        usage = random.randint(1, 10)
        cost = random.randint(1, 10)
        data = [
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 1, 13, 0, 0),
                "usage_end_time": datetime(2022, 1, 1, 14, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
                "resource_name": "instance-1",
                "resource_global_name": "//compute.googleapis.com/projects/1234/zones/us-central1-a/instances/1234",
            },
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 1, 14, 0, 0),
                "usage_end_time": datetime(2022, 1, 1, 15, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
                "resource_name": "instance-1",
                "resource_global_name": "//compute.googleapis.com/projects/1234/zones/us-central1-a/instances/1234",
            },
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 2, 4, 0, 0),
                "usage_end_time": datetime(2022, 1, 2, 5, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
                "resource_name": "instance-1",
                "resource_global_name": "//compute.googleapis.com/projects/1234/zones/us-central1-a/instances/1234",
            },
        ]
        df = DataFrame(data)

        daily_df = self.post_processor._generate_daily_data(df)

        first_day = daily_df[daily_df["usage_start_time"] == "2022-01-01"]
        second_day = daily_df[daily_df["usage_start_time"] == "2022-01-02"]

        self.assertEqual(first_day.shape[0], 1)
        self.assertEqual(second_day.shape[0], 1)

        self.assertTrue((first_day["cost"] == cost * 2).any(bool_only=True))
        self.assertTrue((second_day["cost"] == cost).any(bool_only=True))
        self.assertTrue((first_day["usage_amount_in_pricing_units"] == usage * 2).any(bool_only=True))
        self.assertTrue((second_day["usage_amount_in_pricing_units"] == usage).any(bool_only=True))

    def test_gcp_generate_daily_w_resource_data(self):
        """Test that we aggregate data at a daily level w/o resource names."""
        usage = random.randint(1, 10)
        cost = random.randint(1, 10)
        data = [
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 1, 13, 0, 0),
                "usage_end_time": datetime(2022, 1, 1, 14, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
                "resource_name": None,
                "resource_global_name": None,
            },
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 1, 14, 0, 0),
                "usage_end_time": datetime(2022, 1, 1, 15, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
                "resource_name": None,
                "resource_global_name": None,
            },
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 2, 4, 0, 0),
                "usage_end_time": datetime(2022, 1, 2, 5, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
                "resource_name": None,
                "resource_global_name": None,
            },
        ]
        df = DataFrame(data)
        daily_df = self.post_processor._generate_daily_data(df)

        first_day = daily_df[daily_df["usage_start_time"] == "2022-01-01"]
        second_day = daily_df[daily_df["usage_start_time"] == "2022-01-02"]

        self.assertTrue((first_day["cost"] == cost * 2).any(bool_only=True))
        self.assertTrue((second_day["cost"] == cost).any(bool_only=True))
        self.assertTrue((first_day["usage_amount_in_pricing_units"] == usage * 2).any(bool_only=True))
        self.assertTrue((second_day["usage_amount_in_pricing_units"] == usage).any(bool_only=True))

    def test_gcp_generate_daily_wo_resource_data(self):
        """Test that we aggregate data at a daily level w/o resource names."""
        usage = random.randint(1, 10)
        cost = random.randint(1, 10)
        data = [
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 1, 13, 0, 0),
                "usage_end_time": datetime(2022, 1, 1, 14, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
            },
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 1, 14, 0, 0),
                "usage_end_time": datetime(2022, 1, 1, 15, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
            },
            {
                "billing_account_id": "fact",
                "service_id": "95FF-2EF5-5EA1",
                "service_description": "Cloud Storage",
                "sku_id": "E5F0-6A5D-7BAD",
                "sku_description": "Standard Storage US Regional",
                "usage_start_time": datetime(2022, 1, 2, 4, 0, 0),
                "usage_end_time": datetime(2022, 1, 2, 5, 0, 0),
                "project_id": "trouble-although-mind",
                "project_name": "trouble-although-mind",
                "labels": '{"key": "test_storage_key", "value": "test_storage_label"}',
                "system_labels": "{}",
                "cost_type": "regular",
                "credits": "{}",
                "location_region": "us-central1",
                "usage_pricing_unit": "byte-seconds",
                "usage_amount_in_pricing_units": usage,
                "currency": "USD",
                "cost": cost,
                "invoice_month": "202201",
            },
        ]
        df = DataFrame(data)
        daily_df = self.post_processor._generate_daily_data(df)

        first_day = daily_df[daily_df["usage_start_time"] == "2022-01-01"]
        second_day = daily_df[daily_df["usage_start_time"] == "2022-01-02"]

        self.assertEqual(first_day.shape[0], 1)
        self.assertEqual(second_day.shape[0], 1)

        self.assertTrue((first_day["cost"] == cost * 2).any(bool_only=True))
        self.assertTrue((second_day["cost"] == cost).any(bool_only=True))
        self.assertTrue((first_day["usage_amount_in_pricing_units"] == usage * 2).any(bool_only=True))
        self.assertTrue((second_day["usage_amount_in_pricing_units"] == usage).any(bool_only=True))

    def test_empty_dataframe_during_daily_data_generation(self):
        """Test an empty dataframe is returned."""
        # if we have an empty data frame, we should get one back
        result = self.post_processor._generate_daily_data(DataFrame())
        self.assertTrue(result.empty)

    def test_gcp_process_dataframe(self):
        """Test that data frame post processing succeeds."""
        data = {
            "column.one": [1, 2, 3],
            "column.two": [4, 5, 6],
            "three": [7, 8, 9],
            "labels": ['{"label_one": "value_one"}', '{"label_one": "value_two"}', '{"label_two": "value_three"}'],
        }
        expected_columns = ["column_one", "column_two", "labels", "three"]

        df = DataFrame(data)

        expected_tags = {"label_one", "label_two"}
        with patch("masu.util.gcp.gcp_post_processor.GCPPostProcessor._generate_daily_data"):
            result_df, _ = self.post_processor.process_dataframe(df)
            self.assertIsInstance(self.post_processor.enabled_tag_keys, set)
            self.assertEqual(self.post_processor.enabled_tag_keys, expected_tags)

            result_columns = list(result_df)
            self.assertEqual(sorted(result_columns), sorted(expected_columns))

    def test_process_gcp_credits(self):
        """Test that credits are formatted properly with a valid JSON string"""
        csv_converters, panda_kwargs = self.post_processor.get_column_converters(["credits"], {})
        self.assertEqual({}, panda_kwargs)
        credit_converter = csv_converters.get("credits")
        credit_string = '[{"first": "yes", "second": "None", "third": "no"}]'

        expected = '{"first": "yes", "second": "None", "third": "no"}'
        credit_result = credit_converter(credit_string)
        self.assertEqual(credit_result, expected)

    def test_process_gcp_credits_non_standard_fallback(self):
        """Test that credits are formatted properly for a non-standard JSON string"""
        credit_string = "[{'first': 'yes', 'second': None, 'third': 'no'}]"
        expected = '{"first": "yes", "second": "None", "third": "no"}'

        credit_result = process_gcp_credits(credit_string)

        self.assertEqual(credit_result, expected)

    def test_process_gcp_credits_invalid(self):
        """Test that a warning is logged for an invalid JSON string"""
        credit_string = "[{'first': 'yes', 'second': \"Acme's HQ\", 'third': 'no'}]"

        with self.assertLogs("masu.util.gcp.gcp_post_processor", level="WARNING") as log:
            credit_result = process_gcp_credits(credit_string)

        self.assertIn("unable to process gcp credits", log.output[0].lower())
        self.assertEqual(credit_result, "{}")

    def test_process_gcp_labels(self):
        """Test that labels are formatted properly."""
        csv_converters, panda_kwargs = self.post_processor.get_column_converters(["labels"], {})
        self.assertEqual({}, panda_kwargs)
        label_converter = csv_converters.get("labels")
        label_string = '[{"key": "key_one", "value": "value_one"}, {"key": "key_two", "value": "value_two"}]'

        expected = '{"key_one": "value_one", "key_two": "value_two"}'
        label_result = label_converter(label_string)

        self.assertEqual(label_result, expected)
        # Test label empty set
        label_string = label_converter([])
        self.assertEqual(label_converter(label_string), str({}))

    def test_finalize_post_processing(self):
        """Test that the finalize post processing functionality works.

        Note: For this test we want to process multiple dataframes
        and make sure all keys are found in the db after finalization.
        """
        expected_tag_keys = []
        for idx in range(2):
            expected_tag_key = f"tag_key{idx}"
            expected_tag_keys.append(expected_tag_key)
            lables = []
            for abc in ["A", "B", "C"]:
                lables.append(str({expected_tag_key: f"val{idx}{abc}"}).replace("'", '"'))
            data = {
                "column.one": [1, 2, 3],
                "column.two": [4, 5, 6],
                "three": [7, 8, 9],
                "labels": lables,
            }
            data_frame = DataFrame.from_dict(data)
            with patch("masu.util.gcp.gcp_post_processor.GCPPostProcessor._generate_daily_data"):
                self.post_processor.process_dataframe(data_frame)
                self.assertIn(expected_tag_key, self.post_processor.enabled_tag_keys)
        self.assertEqual(set(expected_tag_keys), self.post_processor.enabled_tag_keys)
        self.post_processor.finalize_post_processing()

        with schema_context(self.schema):
            tag_key_count = (
                EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_GCP)
                .filter(key__in=expected_tag_keys)
                .count()
            )
            self.assertEqual(tag_key_count, len(expected_tag_keys))
