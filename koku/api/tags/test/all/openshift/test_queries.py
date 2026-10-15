#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP-on-All tag query handler."""
from django_tenants.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.tags.all.openshift.queries import OCPAllTagQueryHandler
from api.tags.all.openshift.view import OCPAllTagView
from koku.koku_test_runner import OCP_ON_AWS_CLUSTER_ID
from koku.koku_test_runner import OCP_ON_AZURE_CLUSTER_ID
from koku.koku_test_runner import OCP_ON_GCP_CLUSTER_ID
from reporting.models import OCPAWSTagsSummary
from reporting.models import OCPAzureTagsSummary
from reporting.models import OCPGCPTagsSummary
from reporting.provider.aws.openshift.models import OCPAWSTagsValues
from reporting.provider.azure.openshift.models import OCPAzureTagsValues
from reporting.provider.gcp.openshift.models import OCPGCPTagsValues


class OCPAllTagQueryHandlerTest(IamTestCase):
    """Tests for the OCP-on-All tag query handler.

    Every cloud in the test fixture carries the same tag keys, so these tests
    filter on the per-cloud cluster id to tell the data sources apart: only the
    OCP-on-AWS summary rows belong to the OCP-on-AWS cluster, and so on.
    """

    # (cluster id, tags summary table, tags values table, account column)
    SOURCES = (
        (OCP_ON_AWS_CLUSTER_ID, OCPAWSTagsSummary, OCPAWSTagsValues, "usage_account_id"),
        (OCP_ON_AZURE_CLUSTER_ID, OCPAzureTagsSummary, OCPAzureTagsValues, "subscription_guid"),
        (OCP_ON_GCP_CLUSTER_ID, OCPGCPTagsSummary, OCPGCPTagsValues, "account_id"),
    )

    def _handler(self, url, key=None):
        """Build a handler, optionally for a single tag key endpoint."""
        query_params = self.mocked_query_params(url, OCPAllTagView)
        if key:
            # the mocked query parameters dont include the key from the url so it needs to be added
            query_params.kwargs = {"key": key}
        return OCPAllTagQueryHandler(query_params)

    def test_execute_query_returns_tags_for_every_cloud(self):
        """Test that each cloud's tags summary table is queried."""
        for cluster_id, summary_table, _, _ in self.SOURCES:
            with self.subTest(cluster=cluster_id):
                handler = self._handler(f"?filter[cluster]={cluster_id}")
                data = handler.execute_query().get("data")
                self.assertTrue(data, f"no tags returned for {cluster_id}")

                with tenant_context(self.tenant):
                    cloud_keys = set(
                        summary_table.objects.filter(report_period__cluster_id=cluster_id).values_list(
                            "key", flat=True
                        )
                    )
                self.assertTrue(cloud_keys)
                self.assertTrue({row.get("key") for row in data}.issubset(cloud_keys))

    def test_get_tag_keys_returns_keys_for_every_cloud(self):
        """Test that the key_only path queries each cloud's tags summary table."""
        for cluster_id, summary_table, _, _ in self.SOURCES:
            with self.subTest(cluster=cluster_id):
                handler = self._handler(f"?key_only=True&filter[cluster]={cluster_id}")
                result = handler.get_tag_keys()
                self.assertTrue(result, f"no tag keys returned for {cluster_id}")

                with tenant_context(self.tenant):
                    cloud_keys = set(
                        summary_table.objects.filter(report_period__cluster_id=cluster_id).values_list(
                            "key", flat=True
                        )
                    )
                self.assertTrue(set(result).issubset(cloud_keys))

    def test_get_tag_values_returns_values_for_every_cloud(self):
        """Test that each cloud's tags values table is queried on a value search."""
        for cluster_id, _, values_table, _ in self.SOURCES:
            with self.subTest(cluster=cluster_id):
                with tenant_context(self.tenant):
                    tag = values_table.objects.filter(cluster_ids__contains=[cluster_id]).first()
                self.assertIsNotNone(tag, f"no tag values loaded for {cluster_id}")

                url = f"/{tag.key}/?filter[value]={tag.value}&filter[cluster]={cluster_id}"
                handler = self._handler(url, key=tag.key)
                result = handler.get_tag_values()
                self.assertTrue(result, f"no tag values returned for {cluster_id}")
                self.assertEqual(result[0].get("key"), tag.key)
                self.assertIn(tag.value, result[0].get("values"))

    def test_account_filter_resolves_for_every_cloud(self):
        """Test that the account filter resolves against every data source.

        Only the AWS summary table has a usage_account_id column; the Azure and
        GCP tables hold the account on subscription_guid and account_id, so
        their data sources have to annotate it.
        """
        for cluster_id, summary_table, _, account_column in self.SOURCES:
            with self.subTest(cluster=cluster_id):
                with tenant_context(self.tenant):
                    account = (
                        summary_table.objects.filter(report_period__cluster_id=cluster_id)
                        .exclude(**{f"{account_column}__isnull": True})
                        .values_list(account_column, flat=True)
                        .first()
                    )
                self.assertIsNotNone(account, f"no account loaded for {cluster_id}")

                handler = self._handler(f"?filter[account]={account}")
                self.assertTrue(handler.get_tag_keys(), f"account filter returned nothing for {cluster_id}")

    def test_gcp_data_source_is_included(self):
        """Test that OCPGCPTagsSummary is queried by verifying GCP-specific data.

        The fixture loads identical tag keys for all clouds, so we can't
        distinguish sources by keys alone. Instead, we filter by a GCP account
        and verify results are returned. Before the fix (GCP missing from
        data_sources), this would return empty.
        """
        with tenant_context(self.tenant):
            gcp_account = (
                OCPGCPTagsSummary.objects.filter(report_period__cluster_id=OCP_ON_GCP_CLUSTER_ID)
                .values_list("account_id", flat=True)
                .first()
            )
        self.assertIsNotNone(gcp_account, "no GCP account data in fixture")

        handler = self._handler(f"?filter[account]={gcp_account}")
        result = handler.get_tag_keys()
        self.assertTrue(result, "GCP account filter returned no tags - GCP source not queried")
