#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCP common util."""
import random
from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta
from tenant_schemas.utils import schema_context

from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.util.gcp import common as utils
from reporting.provider.gcp.models import GCPCostEntryBill


class TestGCPUtils(MasuTestCase):
    """Tests for GCP utilities."""

    def test_get_bill_ids_from_provider(self):
        """Test that bill IDs are returned for an GCP provider."""
        with schema_context(self.schema):
            expected_bill_ids = GCPCostEntryBill.objects.values_list("id")
            expected_bill_ids = sorted([bill_id[0] for bill_id in expected_bill_ids])
        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema)

        with schema_context(self.schema):
            bill_ids = sorted([bill.id for bill in bills])

        self.assertEqual(bill_ids, expected_bill_ids)

        # Try with unknown provider uuid
        bills = utils.get_bills_from_provider(self.unkown_test_provider_uuid, self.schema)
        self.assertEqual(bills, [])

    def test_get_bill_ids_from_provider_with_start_date(self):
        """Test that bill IDs are returned for an GCP provider with start date."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.gcp_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with GCPReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__gte=end_date.date()).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema, start_date=end_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_end_date(self):
        """Test that bill IDs are returned for an GCP provider with end date."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.gcp_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with GCPReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = bills.filter(billing_period_start__lte=start_date.date()).all()
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema, end_date=start_date)
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_get_bill_ids_from_provider_with_start_and_end_date(self):
        """Test that bill IDs are returned for an GCP provider with both dates."""
        date_accessor = DateAccessor()

        with ProviderDBAccessor(provider_uuid=self.gcp_provider_uuid) as provider_accessor:
            provider = provider_accessor.get_provider()
        with GCPReportDBAccessor(schema=self.schema) as accessor:

            end_date = date_accessor.today_with_timezone("utc").replace(day=1)
            start_date = end_date
            for i in range(2):
                start_date = start_date - relativedelta(months=i)

            bills = accessor.get_cost_entry_bills_query_by_provider(provider.uuid)
            with schema_context(self.schema):
                bills = (
                    bills.filter(billing_period_start__gte=start_date.date())
                    .filter(billing_period_start__lte=end_date.date())
                    .all()
                )
                expected_bill_ids = [str(bill.id) for bill in bills]

        bills = utils.get_bills_from_provider(
            self.gcp_provider_uuid, self.schema, start_date=start_date, end_date=end_date
        )
        with schema_context(self.schema):
            bill_ids = [str(bill.id) for bill in bills]

        self.assertEqual(bill_ids, expected_bill_ids)

    def test_process_gcp_labels(self):
        """Test that labels are formatted properly."""
        label_string = "[{'key': 'key_one', 'value': 'value_one'}, {'key': 'key_two', 'value': 'value_two'}]"

        expected = '{"key_one": "value_one", "key_two": "value_two"}'
        label_result = utils.process_gcp_labels(label_string)

        self.assertEqual(label_result, expected)

    def test_process_gcp_credits(self):
        """Test that credits are formatted properly."""
        credit_string = "[{'first': 'yes', 'second': None, 'third': 'no'}]"

        expected = '{"first": "yes", "second": "None", "third": "no"}'
        credit_result = utils.process_gcp_credits(credit_string)

        self.assertEqual(credit_result, expected)

    def test_post_processor(self):
        """Test that data frame post processing succeeds."""
        data = {
            "column.one": [1, 2, 3],
            "column.two": [4, 5, 6],
            "three": [7, 8, 9],
            "labels": ['{"label_one": "value_one"}', '{"label_one": "value_two"}', '{"label_two": "value_three"}'],
        }
        expected_columns = ["column_one", "column_two", "labels", "three"]

        df = pd.DataFrame(data)

        expected_tags = {"label_one", "label_two"}
        result_df = utils.gcp_post_processor(df)
        self.assertIsInstance(result_df, tuple)
        result_df, df_tag_keys = result_df
        self.assertIsInstance(df_tag_keys, set)
        self.assertEqual(df_tag_keys, expected_tags)

        result_columns = list(result_df)
        self.assertEqual(sorted(result_columns), sorted(expected_columns))

    def test_match_openshift_resources_and_labels(self):
        """Test that OCP on GCP matching occurs."""
        cluster_topology = {
            "resource_ids": [],
            "cluster_id": "ocp-gcp-cluster",
            "cluster_alias": "my-ocp-cluster",
            "nodes": ["id1", "id2", "id3"],
            "projects": [],
        }

        matched_tags = []

        # in the gcp dataframe, these are labels
        data = [
            {
                "resourceid": "id1",
                "pretaxcost": 1,
                "labels": '{"key": "value", "kubernetes-io-cluster-ocp-gcp-cluster": "owned"}',
            },
            {
                "resourceid": "id2",
                "pretaxcost": 1,
                "labels": '{"key": "other_value", "kubernetes-io-cluster-ocp-gcp-cluster": "owned"}',
            },
            {
                "resourceid": "id3",
                "pretaxcost": 1,
                "labels": '{"key": "other_value", "kubernetes-not-io-cluster-ocp-gcp-cluster": "owned"}',
            },
        ]

        df = pd.DataFrame(data)

        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # kubernetes-io-cluster matching, 2 results should come back with no matched tags
        self.assertEqual(matched_df.shape[0], 2)

        matched_tags = [{"key": "other_value"}]
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)
        # tag matching
        result = matched_df[matched_df["resourceid"] == "id2"]["matched_tag"] == '"key": "other_value"'
        self.assertTrue(result.bool())

        result = matched_df[matched_df["resourceid"] == "id3"]["matched_tag"] == '"key": "other_value"'
        self.assertTrue(result.bool())

        # Matched tags, but none that match the dataset
        matched_tags = [{"something_else": "entirely"}]
        matched_df = utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)

        # kubernetes-io-cluster matching, 2 results should come back but no matched tags
        self.assertEqual(matched_df.shape[0], 2)

        # tag matching
        self.assertFalse((matched_df["matched_tag"] != "").any())

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
        df = pd.DataFrame(data)

        daily_df = utils.gcp_generate_daily_data(df)

        first_day = daily_df[daily_df["usage_start_time"] == "2022-01-01"]
        second_day = daily_df[daily_df["usage_start_time"] == "2022-01-02"]

        self.assertEqual(first_day.shape[0], 1)
        self.assertEqual(second_day.shape[0], 1)

        self.assertTrue((first_day["cost"] == cost * 2).bool())
        self.assertTrue((second_day["cost"] == cost).bool())
        self.assertTrue((first_day["usage_amount_in_pricing_units"] == usage * 2).bool())
        self.assertTrue((second_day["usage_amount_in_pricing_units"] == usage).bool())
