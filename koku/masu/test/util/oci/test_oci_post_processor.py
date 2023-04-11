"""Masu OCI post processor module tests."""
#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import random
from datetime import datetime
from unittest.mock import patch

from pandas import DataFrame

from masu.test import MasuTestCase
from masu.util.oci.oci_post_processor import OCIPostProcessor
from reporting.provider.oci.models import TRINO_REQUIRED_COLUMNS


class TestOCIPostProcessor(MasuTestCase):
    """Test OCI Post Processor."""

    def setUp(self):
        """Set up the test."""
        super().setUp()
        self.post_processor = OCIPostProcessor(self.schema)

    def test_oci_generate_daily_data_cost(self):
        """Test that we aggregate data at a daily level."""
        cost = random.randint(1, 10)
        data = [
            {
                "lineitem_referenceno": "id1",
                "lineitem_tenantid": "my-tenant",
                "lineitem_intervalusagestart": datetime(2021, 6, 7, 11, 24, 0),
                "lineitem_intervalusageend": datetime(2021, 6, 7, 11, 24, 0),
                "product_service": "service",
                "product_resource": "resource",
                "product_compartmentid": "compart_id",
                "product_compartmentname": "compart_name",
                "product_region": "my-region",
                "product_availabilitydomain": "my-domain",
                "product_resourceid": "id4",
                "usage_billedquantity": "3",
                "usage_billedquantityoverage": "0",
                "usage_consumedquantityunits": "BYTES",
                "usage_consumedquantitymeasure": "BYTES",
                "cost_subscriptionid": "subscript_id",
                "cost_productsku": "sku",
                "product_description": "storage",
                "cost_unitprice": "10",
                "cost_unitpriceoverage": "10",
                "cost_mycost": cost,
                "cost_mycostoverage": "0",
                "cost_currencycode": "USD",
                "cost_billingunitreadable": "",
                "cost_skuunitdescription": "unitdescription",
                "cost_overageflag": "",
                "lineitem_iscorrection": "",
                "lineitem_backreferenceno": "",
                "tags": "",
            },
            {
                "lineitem_referenceno": "id1",
                "lineitem_tenantid": "my-tenant",
                "lineitem_intervalusagestart": datetime(2021, 6, 7, 12, 24, 0),  # different hour, same day
                "lineitem_intervalusageend": datetime(2021, 6, 7, 12, 24, 0),  # different hour, same day
                "product_service": "service",
                "product_resource": "resource",
                "product_compartmentid": "compart_id",
                "product_compartmentname": "compart_name",
                "product_region": "my-region",
                "product_availabilitydomain": "my-domain",
                "product_resourceid": "id4",
                "usage_billedquantity": "3",
                "usage_billedquantityoverage": "0",
                "usage_consumedquantityunits": "BYTES",
                "usage_consumedquantitymeasure": "BYTES",
                "cost_subscriptiond": "subscript_id",
                "cost_productsku": "sku",
                "product_description": "storage",
                "cost_unitprice": "10",
                "cost_unitpriceoverage": "10",
                "cost_mycost": cost,
                "cost_mycostoverage": "0",
                "cost_currencycode": "USD",
                "cost_billingunitreadable": "",
                "cost_skuunitdescription": "unitdescription",
                "cost_overageflag": "",
                "lineitem_iscorrection": "",
                "lineitem_backreferenceno": "",
                "tags": "",
            },
            {
                "lineitem_referenceno": "id1",
                "lineitem_tenantid": "my-tenant",
                "lineitem_intervalusagestart": datetime(2021, 6, 8, 12, 24, 0),  # different hour, same day
                "lineitem_intervalusageend": datetime(2021, 6, 8, 12, 24, 0),  # different hour, same day
                "product_service": "service",
                "product_resource": "resource",
                "product_compartmentid": "compart_id",
                "product_compartmentname": "compart_name",
                "product_region": "my-region",
                "product_availabilitydomain": "my-domain",
                "product_resourceid": "id4",
                "usage_billedquantity": "3",
                "usage_billedquantityoverage": "0",
                "usage_consumedquantityunits": "BYTES",
                "usage_consumedquantitymeasure": "BYTES",
                "cost_subscriptionid": "subscript_id",
                "cost_productsku": "sku",
                "product_description": "storage",
                "cost_unitprice": "10",
                "cost_unitpriceoverage": "10",
                "cost_mycost": cost,
                "cost_mycostoverage": "0",
                "cost_currencycode": "USD",
                "cost_billingunitreadable": "",
                "cost_skuunitdescription": "unitdescription",
                "cost_overageflag": "",
                "lineitem_iscorrection": "",
                "lineitem_backreferenceno": "",
                "tags": "",
            },
        ]

        df = DataFrame(data)
        daily_df = self.post_processor._generate_daily_data(df)

        first_day = daily_df[daily_df["lineitem_intervalusagestart"] == "2021-06-07"]
        second_day = daily_df[daily_df["lineitem_intervalusagestart"] == "2021-06-08"]

        # Assert that there is only 1 record per day
        self.assertEqual(first_day.shape[0], 1)
        self.assertEqual(second_day.shape[0], 1)

        self.assertTrue((first_day["cost_mycost"] == cost * 2).bool())

        self.assertTrue((second_day["cost_mycost"] == cost).bool())

    def test_oci_post_processor_empty_tags(self):
        """Test that missing columns in a report end up in the data frame."""
        column_one = "column_one"
        column_two = "column_two"
        column_three = "column-three"
        column_four = "resourceTags/System:key"
        data = {column_one: [1, 2], column_two: [3, 4], column_three: [5, 6], column_four: ["value_1", "value_2"]}
        data_frame = DataFrame.from_dict(data)

        with patch("masu.util.oci.oci_post_processor.OCIPostProcessor._generate_daily_data"):
            processed_data_frame, _ = self.post_processor.process_dataframe(data_frame)
            self.assertIsInstance(self.post_processor.enabled_tag_keys, set)
            self.assertFalse(processed_data_frame["tags"].isna().values.any())

    def test_oci_process_dataframe(self):
        """Test that missing columns in a report end up in the data frame."""
        column_one = "column_one"
        column_two = "column_two"
        column_three = "column-three"
        column_four = "resourceTags/User:key"
        data = {column_one: [1, 2], column_two: [3, 4], column_three: [5, 6], column_four: ["value_1", "value_2"]}
        data_frame = DataFrame.from_dict(data)

        with patch("masu.util.oci.oci_post_processor.OCIPostProcessor._generate_daily_data"):
            processed_data_frame, _ = self.post_processor.process_dataframe(data_frame)
            self.assertIsInstance(self.post_processor.enabled_tag_keys, set)
            columns = list(processed_data_frame)
            self.assertIn(column_one, columns)
            self.assertIn(column_two, columns)
            self.assertIn(column_three.replace("-", "_"), columns)
            self.assertNotIn(column_four, columns)
            self.assertIn("tags", columns)
            for column in TRINO_REQUIRED_COLUMNS:
                self.assertIn(column.replace("-", "_").replace("/", "_").replace(":", "_").lower(), columns)

    def test_oci_generate_daily_data_usage(self):
        """Test that we aggregate data at a daily level."""
        usageamount = random.randint(1, 10)
        data = [
            {
                "lineitem_referenceno": "id1",
                "lineitem_tenantid": "my-tenant",
                "lineitem_intervalusagestart": datetime(2021, 6, 7, 11, 24, 0),
                "lineitem_intervalusageend": datetime(2021, 6, 7, 11, 24, 0),
                "product_service": "service",
                "product_resource": "resource",
                "product_compartmentid": "compart_id",
                "product_compartmentname": "compart_name",
                "product_region": "my-region",
                "product_availabilitydomain": "my-domain",
                "product_resourceid": "id4",
                "usage_consumedquantity": usageamount,
                "usage_billedquantity": "3",
                "usage_billedquantityoverage": "0",
                "usage_consumedquantityunits": "BYTES",
                "usage_consumedquantitymeasure": "BYTES",
                "cost_subscriptionid": "subscript_id",
                "cost_productsku": "sku",
                "product_description": "storage",
                "lineitem_iscorrection": "",
                "lineitem_backreferenceno": "",
                "tags": "",
            },
            {
                "lineitem_referenceno": "id1",
                "lineitem_tenantid": "my-tenant",
                "lineitem_intervalusagestart": datetime(2021, 6, 7, 12, 24, 0),  # different hour, same day
                "lineitem_intervalusageend": datetime(2021, 6, 7, 12, 24, 0),  # different hour, same day
                "product_service": "service",
                "product_resource": "resource",
                "product_compartmentid": "compart_id",
                "product_compartmentname": "compart_name",
                "product_region": "my-region",
                "product_availabilitydomain": "my-domain",
                "product_resourceid": "id4",
                "usage_consumedquantity": usageamount,
                "usage_billedquantity": "3",
                "usage_billedquantityoverage": "0",
                "usage_consumedquantityunits": "BYTES",
                "usage_consumedquantitymeasure": "BYTES",
                "cost_subscriptiond": "subscript_id",
                "cost_productsku": "sku",
                "product_description": "storage",
                "lineitem_iscorrection": "",
                "lineitem_backreferenceno": "",
                "tags": "",
            },
            {
                "lineitem_referenceno": "id1",
                "lineitem_tenantid": "my-tenant",
                "lineitem_intervalusagestart": datetime(2021, 6, 8, 12, 24, 0),  # different hour, same day
                "lineitem_intervalusageend": datetime(2021, 6, 8, 12, 24, 0),  # different hour, same day
                "product_service": "service",
                "product_resource": "resource",
                "product_compartmentid": "compart_id",
                "product_compartmentname": "compart_name",
                "product_region": "my-region",
                "product_availabilitydomain": "my-domain",
                "product_resourceid": "id4",
                "usage_consumedquantity": usageamount,
                "usage_billedquantity": "3",
                "usage_billedquantityoverage": "0",
                "usage_consumedquantityunits": "BYTES",
                "usage_consumedquantitymeasure": "BYTES",
                "cost_subscriptionid": "subscript_id",
                "cost_productsku": "sku",
                "product_description": "storage",
                "lineitem_iscorrection": "",
                "lineitem_backreferenceno": "",
                "tags": "",
            },
        ]

        df = DataFrame(data)

        daily_df = self.post_processor._generate_daily_data(df)

        first_day = daily_df[daily_df["lineitem_intervalusagestart"] == "2021-06-07"]
        second_day = daily_df[daily_df["lineitem_intervalusagestart"] == "2021-06-08"]

        # Assert that there is only 1 record per day
        self.assertEqual(first_day.shape[0], 1)
        self.assertEqual(second_day.shape[0], 1)

        self.assertTrue((first_day["usage_consumedquantity"] == usageamount * 2).bool())

        self.assertTrue((second_day["usage_consumedquantity"] == usageamount).bool())
