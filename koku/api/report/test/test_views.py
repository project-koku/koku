#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report views."""
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.common.pagination import ReportPagination
from api.common.pagination import ReportRankedPagination
from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.report.view import get_paginator
from api.utils import DateHelper


class ReportViewTest(IamTestCase):
    """Tests the report view."""

    ENDPOINTS_AWS = ["reports-aws-costs", "reports-aws-storage", "reports-aws-instance-type"]
    ENDPOINTS_GCP = ["reports-gcp-costs"]
    ENDPOINTS_AZURE = ["reports-azure-costs", "reports-azure-storage", "reports-azure-instance-type"]
    ENDPOINTS_OPENSHIFT = [
        "reports-openshift-costs",
        "reports-openshift-memory",
        "reports-openshift-cpu",
        "reports-openshift-volume",
    ]
    ENDPOINTS_OPENSHIFT_AWS = [
        "reports-openshift-aws-costs",
        "reports-openshift-aws-storage",
        "reports-openshift-aws-instance-type",
    ]
    ENDPOINTS_OPENSHIFT_AZURE = [
        "reports-openshift-azure-costs",
        "reports-openshift-azure-storage",
        "reports-openshift-azure-instance-type",
    ]
    ENDPOINTS_OPENSHIFT_ALL = [
        "reports-openshift-all-costs",
        "reports-openshift-all-storage",
        "reports-openshift-all-instance-type",
    ]
    ENDPOINTS = (
        ENDPOINTS_AWS
        + ENDPOINTS_GCP
        + ENDPOINTS_AZURE
        + ENDPOINTS_OPENSHIFT
        + ENDPOINTS_OPENSHIFT_AWS
        + ENDPOINTS_OPENSHIFT_AZURE
        + ENDPOINTS_OPENSHIFT_ALL
    )

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()
        self.factory = RequestFactory()

    def test_endpoint_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertTrue(len(json_result.get("data")) > 0)

    def test_endpoints_date_query_param(self):
        """Test endpoint runs with an invalid query param."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                query = f"order_by[date]={str(DateHelper().today.date())}&group_by[tag:app]=*"
                url = f"{reverse(endpoint)}?{query}"
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                meta_result = response.json().get("meta")
                self.assertIsNotNone(meta_result)
                self.assertTrue("date" in meta_result.get("order_by") or [])

    def test_endpoints_invalid_query_param(self):
        """Test endpoint runs with an invalid query param."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                query = "group_by[invalid]=*"
                url = f"{reverse(endpoint)}?{query}"
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endpoint_csv(self):
        """Test CSV output of inventory endpoint reports."""
        self.client = APIClient(HTTP_ACCEPT="text/csv")
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, content_type="text/csv", **self.headers)
                response.render()

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.accepted_media_type, "text/csv")
                self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_paginator_default(self):
        """Test that the standard report paginator is returned."""
        params = {}
        paginator = get_paginator(params, 0)
        self.assertIsInstance(paginator, ReportPagination)

    def test_get_paginator_for_filter_offset(self):
        """Test that the standard report paginator is returned."""
        params = {"offset": 5}
        paginator = get_paginator(params, 0)
        self.assertIsInstance(paginator, ReportRankedPagination)

    @RbacPermissions({"invalid.permissions": {"things": ["thing_1", "thing_2"]}})
    def test_rbacpermissions_invalid(self):
        """Test that endpoints reject invalid permissions."""
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_rbacpermissions_valid_aws(self):
        """Test that AWS endpoints accept valid AWS permissions."""
        for endpoint in self.ENDPOINTS_AWS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"gcp.account": {"read": ["*"]}})
    def test_rbacpermissions_valid_gcp(self):
        """Test that GCP endpoints accept valid GCP permissions."""
        for endpoint in self.ENDPOINTS_GCP:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"azure.subscription_guid": {"read": ["*"]}})
    def test_rbacpermissions_valid_azure(self):
        """Test that Azure endpoints accept valid Azure permissions."""
        for endpoint in self.ENDPOINTS_AZURE:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}})
    def test_rbacpermissions_valid_openshift(self):
        """Test that OpenShift endpoints accept valid OpenShift permissions."""
        for endpoint in self.ENDPOINTS_OPENSHIFT:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
