#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
from django.db.models import F
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummary
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummary
from reporting.provider.ocp.models import OCPCostSummaryByProjectP


class ResourceTypesViewTestOpenshiftProjects(IamTestCase):
    """Tests the resource types views."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()

    @RbacPermissions({"openshift.project": {"read": ["cost-management"]}})
    def test_openshift_project_with_project_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByProjectP.objects.annotate(**{"value": F("namespace")})
                .values("value")
                .distinct()
                .filter(namespace__in=["cost-management"])
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}})
    def test_openshift_project_with_cluster_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByProjectP.objects.annotate(**{"value": F("namespace")})
                .values("value")
                .distinct()
                .filter(cluster_id__in=["OCP-on-AWS"])
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions(
        {"openshift.cluster": {"read": ["OCP-on-AWS"]}, "openshift.project": {"read": ["cost-management"]}}
    )
    def test_openshift_project_with_cluster_and_project_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByProjectP.objects.annotate(**{"value": F("namespace")})
                .values("value")
                .distinct()
                .filter(namespace__in=["cost-management"], cluster_id__in=["OCP-on-AWS"])
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}, "openshift.project": {"read": ["*"]}})
    def test_openshift_project_with_cluster_and_all_project_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByProjectP.objects.annotate(**{"value": F("namespace")})
                .values("value")
                .distinct()
                .filter(cluster_id__in=["OCP-on-AWS"])
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.project": {"read": ["cost-management"]}})
    def test_openshift_project_with_all_cluster_and_project_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByProjectP.objects.annotate(**{"value": F("namespace")})
                .values("value")
                .distinct()
                .filter(namespace__in=["cost-management"])
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    def test_openshift_project_on_cloud_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                (
                    OCPAWSCostLineItemProjectDailySummary.objects.annotate(**{"value": F("namespace")})
                    .values("value")
                    .distinct()
                    .filter(namespace__isnull=False)
                )
                .union(
                    (
                        OCPAzureCostLineItemProjectDailySummary.objects.annotate(**{"value": F("namespace")})
                        .values("value")
                        .distinct()
                        .filter(namespace__isnull=False)
                    ),
                    all=True,
                )
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        qs = "?cloud=true"
        url = reverse("openshift-projects") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)
