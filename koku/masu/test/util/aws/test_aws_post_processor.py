"""Masu AWS post processor module tests."""
#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import random
from datetime import datetime
from unittest.mock import patch

from django_tenants.utils import schema_context
from pandas import DataFrame

from api.provider.models import Provider
from masu.test import MasuTestCase
from masu.util.aws.aws_post_processor import AWSPostProcessor
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.aws.models import AWSEnabledCategoryKeys
from reporting.provider.aws.models import TRINO_REQUIRED_COLUMNS


class TestAWSPostProcessor(MasuTestCase):
    """Test AWS Post Processor."""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.post_processor = AWSPostProcessor(self.schema)

    def test_aws_generate_daily_data(self):
        """Test that we aggregate data at a daily level."""
        lineitem_usageamount = random.randint(1, 10)
        lineitem_unblendedcost = random.randint(1, 10)
        lineitem_unblendedrate = random.randint(1, 10)
        data = [
            {
                "lineitem_resourceid": "id1",
                "lineitem_usagestartdate": datetime(2021, 6, 7, 11, 24, 0),
                "bill_invoiceid": 123,
                "bill_payeraccountid": 1,
                "lineitem_usageaccountid": 1,
                "lineitem_legalentity": "Red Hat",
                "lineitem_lineitemdescription": "Red Hat",
                "lineitem_productcode": "ec2",
                "lineitem_availabilityzone": "us-east-1a",
                "lineitem_lineitemtype": "SavingsPlanCoveredUsage",
                "bill_billingentity": "AWS Marketplace",
                "product_productfamily": "compute",
                "product_productname": "AmazonEC2",
                "product_instancetype": "t2.micro",
                "product_region": "us-east-1",
                "pricing_unit": "hours",
                "resourcetags": '{"key": "value"}',
                "costcategory": '{"cat": "egory"}',
                "lineitem_usageamount": lineitem_usageamount,
                "lineitem_normalizationfactor": 1,
                "lineitem_normalizedusageamount": 1,
                "lineitem_currencycode": "USD",
                "lineitem_unblendedrate": lineitem_unblendedrate,
                "lineitem_unblendedcost": lineitem_unblendedcost,
                "lineitem_blendedrate": 1,
                "lineitem_blendedcost": 1,
                "savingsplan_savingsplaneffectivecost": 1,
                "pricing_publicondemandcost": 1,
                "pricing_publicondemandrate": 1,
            },
            {
                "lineitem_resourceid": "id1",
                "lineitem_usagestartdate": datetime(2021, 6, 7, 12, 24, 0),  # different hour, same day
                "bill_invoiceid": 123,
                "bill_payeraccountid": 1,
                "lineitem_usageaccountid": 1,
                "lineitem_legalentity": "Red Hat",
                "lineitem_lineitemdescription": "Red Hat",
                "lineitem_productcode": "ec2",
                "lineitem_availabilityzone": "us-east-1a",
                "lineitem_lineitemtype": "SavingsPlanCoveredUsage",
                "bill_billingentity": "AWS Marketplace",
                "product_productfamily": "compute",
                "product_productname": "AmazonEC2",
                "product_instancetype": "t2.micro",
                "product_region": "us-east-1",
                "pricing_unit": "hours",
                "resourcetags": '{"key": "value"}',
                "costcategory": '{"cat": "egory"}',
                "lineitem_usageamount": lineitem_usageamount,
                "lineitem_normalizationfactor": 1,
                "lineitem_normalizedusageamount": 1,
                "lineitem_currencycode": "USD",
                "lineitem_unblendedrate": lineitem_unblendedrate,
                "lineitem_unblendedcost": lineitem_unblendedcost,
                "lineitem_blendedrate": 1,
                "lineitem_blendedcost": 1,
                "savingsplan_savingsplaneffectivecost": 1,
                "pricing_publicondemandcost": 1,
                "pricing_publicondemandrate": 1,
            },
            {
                "lineitem_resourceid": "id1",
                "lineitem_usagestartdate": datetime(2021, 6, 8, 12, 24, 0),  # different day
                "bill_invoiceid": 123,
                "bill_payeraccountid": 1,
                "lineitem_usageaccountid": 1,
                "lineitem_legalentity": "Red Hat",
                "lineitem_lineitemdescription": "Red Hat",
                "lineitem_productcode": "ec2",
                "lineitem_availabilityzone": "us-east-1a",
                "lineitem_lineitemtype": "SavingsPlanCoveredUsage",
                "bill_billingentity": "AWS Marketplace",
                "product_productfamily": "compute",
                "product_productname": "AmazonEC2",
                "product_instancetype": "t2.micro",
                "product_region": "us-east-1",
                "pricing_unit": "hours",
                "resourcetags": '{"key": "value"}',
                "costcategory": '{"cat": "egory"}',
                "lineitem_usageamount": lineitem_usageamount,
                "lineitem_normalizationfactor": 1,
                "lineitem_normalizedusageamount": 1,
                "lineitem_currencycode": "USD",
                "lineitem_unblendedrate": lineitem_unblendedrate,
                "lineitem_unblendedcost": lineitem_unblendedcost,
                "lineitem_blendedrate": 1,
                "lineitem_blendedcost": 1,
                "savingsplan_savingsplaneffectivecost": 1,
                "pricing_publicondemandcost": 1,
                "pricing_publicondemandrate": 1,
            },
        ]

        df = DataFrame(data)

        daily_df = self.post_processor._generate_daily_data(df)

        first_day = daily_df[daily_df["lineitem_usagestartdate"] == "2021-06-07"]
        second_day = daily_df[daily_df["lineitem_usagestartdate"] == "2021-06-08"]

        # Assert that there is only 1 record per day
        self.assertEqual(first_day.shape[0], 1)
        self.assertEqual(second_day.shape[0], 1)

        self.assertTrue((first_day["lineitem_usageamount"] == lineitem_usageamount * 2).bool())
        self.assertTrue((first_day["lineitem_unblendedcost"] == lineitem_unblendedcost * 2).bool())
        self.assertTrue((first_day["lineitem_unblendedrate"] == lineitem_unblendedrate).bool())

        self.assertTrue((second_day["lineitem_usageamount"] == lineitem_usageamount).bool())
        self.assertTrue((second_day["lineitem_unblendedcost"] == lineitem_unblendedcost).bool())
        self.assertTrue((second_day["lineitem_unblendedrate"] == lineitem_unblendedrate).bool())

    def test_aws_process_dataframe(self):
        """Test that missing columns in a report end up in the data frame."""
        expected_tag_key = "key"
        expected_category_key = "Env"
        data = {
            "column_one": [1, 2],
            "column_two": [3, 4],
            "column-three": [5, 6],
            "resourceTags/user:key": ["value_1", "value_2"],
            "costCategory/Env": ["prod", "stage"],
        }
        data_frame = DataFrame.from_dict(data)

        with patch("masu.util.aws.aws_post_processor.AWSPostProcessor._generate_daily_data"):
            processed_data_frame, _ = self.post_processor.process_dataframe(data_frame)
            self.assertEqual({expected_category_key}, self.post_processor.enabled_categories)
            self.assertEqual({expected_tag_key}, self.post_processor.enabled_tag_keys)
            columns = list(processed_data_frame)
            for key in data.keys():
                if key == "resourceTags/user:key":
                    self.assertIn("resourcetags", columns)
                elif key == "costCategory/Env":
                    self.assertIn("costcategory", columns)
                else:
                    self.assertIn(key.replace("-", "_"), columns)

            for column in TRINO_REQUIRED_COLUMNS:
                self.assertIn(column.replace("-", "_").replace("/", "_").replace(":", "_").lower(), columns)

    def test_aws_post_processor_customer_filtered_columns(self):
        """Test that customer filtered columns get converted correctly in the data frame."""
        column_one = "bill_bill_type"
        column_two = "line_item_usage_start_date"
        expected_col_one = "bill_billtype"
        expected_col_two = "lineitem_usagestartdate"
        data = {column_one: [1, 2], column_two: [3, 4]}
        data_frame = DataFrame.from_dict(data)

        with patch("masu.util.aws.aws_post_processor.AWSPostProcessor._generate_daily_data"):
            processed_data_frame, _ = self.post_processor.process_dataframe(data_frame)
            self.assertIsInstance(self.post_processor.enabled_categories, set)
            self.assertIsInstance(self.post_processor.enabled_tag_keys, set)
            self.assertIn(expected_col_one, processed_data_frame)
            self.assertIn(expected_col_two, processed_data_frame)
            for column in TRINO_REQUIRED_COLUMNS:
                self.assertIn(
                    column.replace("-", "_").replace("/", "_").replace(":", "_").lower(), processed_data_frame
                )

    def test_aws_post_processor_empty_tags(self):
        """Test that missing columns in a report end up in the data frame."""
        column_one = "column_one"
        column_two = "column_two"
        column_three = "column-three"
        column_four = "resourceTags/System:key"
        data = {column_one: [1, 2], column_two: [3, 4], column_three: [5, 6], column_four: ["value_1", "value_2"]}
        data_frame = DataFrame.from_dict(data)

        with patch("masu.util.aws.aws_post_processor.AWSPostProcessor._generate_daily_data"):
            processed_data_frame, _ = self.post_processor.process_dataframe(data_frame)
            self.assertIsInstance(self.post_processor.enabled_tag_keys, set)
            self.assertFalse(processed_data_frame["resourcetags"].isna().values.any())

    def test_finalize_post_processing(self):
        """Test that the finalize post processing functionality works.

        Note: For this test we want to process multiple dataframes
        and make sure all keys are found in the db after finalization.
        """
        expected_tag_keys = []
        expected_cat_keys = []
        for idx in range(2):
            expected_tag_key = f"tag_key{idx}"
            expected_cat_key = f"cat_key{idx}"
            expected_tag_keys.append(expected_tag_key)
            expected_cat_keys.append(expected_cat_key)
            data = {
                "column_one": [1, 2],
                "column_two": [3, 4],
                "column-three": [5, 6],
                f"resourceTags/user:tag_key{idx}": [f"tag_value_{idx}_A", f"tag_value_{idx}_B"],
                f"costCategory/cat_key{idx}": [f"cat_value_{idx}_A", f"cat_value_{idx}_B"],
            }
            data_frame = DataFrame.from_dict(data)
            with patch("masu.util.aws.aws_post_processor.AWSPostProcessor._generate_daily_data"):
                self.post_processor.process_dataframe(data_frame)
                self.assertIn(expected_tag_key, self.post_processor.enabled_tag_keys)
                self.assertIn(expected_cat_key, self.post_processor.enabled_categories)
        self.assertEqual(set(expected_tag_keys), self.post_processor.enabled_tag_keys)
        self.assertEqual(set(expected_cat_keys), self.post_processor.enabled_categories)
        self.post_processor.finalize_post_processing()

        with schema_context(self.schema):
            cat_key_count = AWSEnabledCategoryKeys.objects.filter(key__in=expected_cat_keys).count()
            self.assertEqual(cat_key_count, len(expected_cat_keys))
            tag_key_count = (
                EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_AWS)
                .filter(key__in=expected_tag_keys)
                .count()
            )
            self.assertEqual(tag_key_count, len(expected_tag_keys))
