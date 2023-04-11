#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the GCP common util."""
from unittest.mock import patch

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
            expected_bill_ids = sorted(bill_id[0] for bill_id in expected_bill_ids)
        bills = utils.get_bills_from_provider(self.gcp_provider_uuid, self.schema)

        with schema_context(self.schema):
            bill_ids = sorted(bill.id for bill in bills)

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

    def test_match_openshift_resources_and_labels(self):
        """Test that OCP on GCP matching occurs."""
        cluster_topology = [
            {
                "resource_ids": [],
                "cluster_id": "ocp-gcp-cluster",
                "cluster_alias": "my-ocp-cluster",
                "nodes": ["id1", "id2", "id3"],
                "projects": [],
                "provider_uuid": "2e26f8a7-42db-4a11-a0b1-f3084cd11e60",
            }
        ]

        matched_tags = []

        # in the gcp dataframe, these are labels
        data = [
            {
                "resourceid": "id1",
                "pretaxcost": 1,
                "resource_name": "",
                "labels": '{"key": "value", "kubernetes-io-cluster-ocp-gcp-cluster": "owned"}',
            },
            {
                "resourceid": "id2",
                "pretaxcost": 1,
                "resource_name": "",
                "labels": '{"key": "other_value", "kubernetes-io-cluster-ocp-gcp-cluster": "owned"}',
            },
            {
                "resourceid": "id3",
                "pretaxcost": 1,
                "resource_name": "",
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

    def test_match_openshift_resources(self):
        """Test that OCP on GCP matching occurs."""
        cluster_topology = [
            {
                "resource_ids": [],
                "cluster_id": "ocp-gcp-cluster",
                "cluster_alias": "my-ocp-cluster",
                "nodes": ["id1", "id2", "id3"],
                "projects": [],
            }
        ]

        # in the gcp dataframe, these are labels
        data = [
            {
                "resourceid": "id1",
                "pretaxcost": 1,
                "resource_name": "resource_1",
                "global_resource_name": "global_resource_1",
                "labels": '{"key": "other_value"}',
            },
            {
                "resourceid": "id2",
                "pretaxcost": 1,
                "resource_name": "resource_2",
                "global_resource_name": "global_resource_2",
                "labels": '{"key": "other_value"}',
            },
            {
                "resourceid": "id3",
                "pretaxcost": 1,
                "resource_name": "resource_2",
                "global_resource_name": "global_resource_3",
                "labels": '{"key": "other_value"}',
            },
        ]

        df = pd.DataFrame(data)
        expected_log = "Matching OpenShift on GCP by resource ID."

        # Matched tags, but none that match the dataset
        matched_tags = [{"something_else": "entirely"}]
        with self.assertLogs("masu.util.gcp.common", level="INFO") as logger:
            utils.match_openshift_resources_and_labels(df, cluster_topology, matched_tags)
            self.assertIn(expected_log, logger.output[0])

    def test_deduplicate_reports_for_gcp(self):
        """Test the deduplication of reports for gcp."""
        expected_results_dict = {
            "202207": {"start": "2022-07-01", "end": "2022-07-21"},
            "202208": {"start": "2022-07-31", "end": "2022-08-30"},
        }
        mocked_reports = [
            {
                "schema_name": "org1234567",
                "provider_type": "GCP",
                "provider_uuid": "1we",
                "manifest_id": 1,
                "tracing_id": "2022-07-20|2022-07-21 02:40:55.848000+00:00",
                "start": "2022-07-01",
                "end": "2022-07-04",
                "invoice_month": "202207",
            },
            {
                "schema_name": "org1234567",
                "provider_type": "GCP",
                "provider_uuid": "1we",
                "manifest_id": 1,
                "tracing_id": "2022-07-20|2022-07-21 02:40:55.848000+00:00",
                "start": "2022-07-19",
                "end": "2022-07-20",
                "invoice_month": "202207",
            },
            {
                "schema_name": "org1234567",
                "provider_type": "GCP",
                "provider_uuid": "1we",
                "manifest_id": 1,
                "tracing_id": "2022-07-20|2022-07-21 02:40:55.848000+00:00",
                "start": "2022-07-19",
                "end": "2022-07-21",
                "invoice_month": "202207",
            },
            {
                "schema_name": "org1234567",
                "provider_type": "GCP",
                "provider_uuid": "1we",
                "manifest_id": 2,
                "tracing_id": "2022-08-01|2022-08-02 01:11:12.066000+00:00",
                "start": "2022-07-31",
                "end": "2022-08-01",
                "invoice_month": "202208",
            },
            {
                "schema_name": "org1234567",
                "provider_type": "GCP",
                "provider_uuid": "1we",
                "manifest_id": 3,
                "tracing_id": "2022-08-03|2022-08-04 01:43:05.921000+00:00",
                "start": "2022-08-23",
                "end": "2022-08-30",
                "invoice_month": "202208",
            },
        ]
        results = utils.deduplicate_reports_for_gcp(mocked_reports)
        self.assertEqual(len(results), 2)
        for result in results:
            result_invoice = result.get("invoice_month")
            expected_dates = expected_results_dict.get(result_invoice)
            self.assertIsNotNone(expected_dates)
            self.assertEqual(expected_dates.get("start"), result.get("start"))
            self.assertEqual(expected_dates.get("end"), result.get("end"))

    @patch("masu.util.gcp.common.AccountsAccessor.get_accounts")
    def test_check_resource_level_invalid_uuid(self, mock_accounts):
        """Test gcp resource level paused source."""
        mock_accounts.return_value = []
        expected_log = "Account not returned, source likely has processing suspended."
        with self.assertLogs("masu.util.gcp.common", level="INFO") as logger:
            result = utils.check_resource_level(self.provider_uuid)
            self.assertFalse(result)
            self.assertIn(expected_log, logger.output[1])
