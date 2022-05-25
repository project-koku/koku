#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
from unittest.mock import patch
from uuid import uuid4

from django.db.models import F
from django.urls import reverse
from rest_framework import status
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import RbacPermissions
from api.utils import DateHelper
from masu.database.oci_report_db_accessor import OCIReportDBAccessor
from masu.test import MasuTestCase
from reporting.provider.oci.models import OCITopology


class ResourceTypesViewTestGcpServices(MasuTestCase):
    """Tests the resource types views."""

    @classmethod
    def setUpClass(cls):
        """Set up the customer view tests."""
        super().setUpClass()
        cls.accessor = OCIReportDBAccessor(schema=cls.schema)

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

    @RbacPermissions({"oci.project": {"read": ["*"]}, "oci.account": {"read": ["example_account_id"]}})
    @patch("masu.database.oci_report_db_accessor.OCIReportDBAccessor.get_oci_topology_trino")
    def test_oci_services_view_with_oci_project_wildcard_and_account_access(self, mock_get_topo):
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
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.accessor.populate_oci_topology_information_tables(self.oci_provider, start_date, end_date)
        with schema_context(self.schema_name):
            expected = (
                OCITopology.objects.annotate(**{"value": F("service_alias")})
                .values("value")
                .distinct()
                .filter(account_id="example_account_id")
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("oci-services")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"oci.project": {"read": ["example-project-id"]}, "oci.account": {"read": ["*"]}})
    @patch("masu.database.oci_report_db_accessor.OCIReportDBAccessor.get_oci_topology_trino")
    def test_oci_services_view_with_oci_account_wildcard_and_project_access(self, mock_get_topo):
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
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.accessor.populate_oci_topology_information_tables(self.oci_provider, start_date, end_date)
        with schema_context(self.schema_name):
            expected = (
                OCITopology.objects.annotate(**{"value": F("service_alias")})
                .values("value")
                .distinct()
                .filter(project_id="example-project-id")
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("oci-services")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)
