#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
from unittest.mock import patch
from uuid import uuid4

from django.db.models import F
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status

from api.iam.test.iam_test_case import RbacPermissions
from api.utils import DateHelper
from masu.database.gcp_report_db_accessor import GCPReportDBAccessor
from masu.test import MasuTestCase
from reporting.provider.gcp.models import GCPTopology


class ResourceTypesViewTestGcpAccounts(MasuTestCase):
    """Tests the resource types views."""

    @classmethod
    def setUpClass(cls):
        """Set up the customer view tests."""
        super().setUpClass()
        cls.accessor = GCPReportDBAccessor(schema=cls.schema)

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.dh = DateHelper()
        self.start_date = self.dh.this_month_start
        self.end_date = self.dh.this_month_end
        self.invoice_month = self.dh.gcp_find_invoice_months_in_date_range(self.start_date, self.end_date)

    @RbacPermissions({"gcp.project": {"read": ["example-project-id"]}, "gcp.account": {"read": ["*"]}})
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.get_gcp_topology_trino")
    def test_gcp_accounts_view_with_gcp_account_wildcard_and_project_access(self, mock_get_topo):
        """Test endpoint runs with a customer owner."""
        source_uuid = uuid4()
        mock_topo_record = [
            (
                source_uuid,
                "example_account_id",
                "example-project-id",
                "The Best Project",
                "Service_1",
                "The Best Service",
                "US East",
            ),
            (
                source_uuid,
                "not_example_account_id",
                "not_example-project-id",
                "The Worst Project",
                "Service_2",
                "The Worst Service",
                "US West",
            ),
        ]
        mock_get_topo.return_value = mock_topo_record
        self.accessor.populate_gcp_topology_information_tables(
            self.gcp_provider, self.start_date, self.end_date, self.invoice_month
        )
        with schema_context(self.schema_name):
            expected = (
                GCPTopology.objects.annotate(**{"value": F("project_id")})
                .values("value")
                .distinct()
                .filter(project_id="example-project-id")
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("gcp-accounts")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"gcp.project": {"read": ["*"]}, "gcp.account": {"read": ["example_account_id"]}})
    @patch("masu.database.gcp_report_db_accessor.GCPReportDBAccessor.get_gcp_topology_trino")
    def test_gcp_accounts_view_with_gcp_project_wildcard_and_account_access(self, mock_get_topo):
        """Test endpoint runs with a customer owner."""
        source_uuid = uuid4()
        mock_topo_record = [
            (
                source_uuid,
                "example_account_id",
                "example-project-id",
                "The Best Project",
                "Service_1",
                "The Best Service",
                "US East",
            ),
            (
                source_uuid,
                "not_example_account_id",
                "not_example-project-id",
                "The Worst Project",
                "Service_2",
                "The Worst Service",
                "US West",
            ),
        ]
        mock_get_topo.return_value = mock_topo_record
        self.accessor.populate_gcp_topology_information_tables(
            self.gcp_provider, self.start_date, self.end_date, self.invoice_month
        )
        with schema_context(self.schema_name):
            expected = (
                GCPTopology.objects.annotate(**{"value": F("account_id")})
                .values("value")
                .distinct()
                .filter(account_id="example_account_id")
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("gcp-accounts")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)
