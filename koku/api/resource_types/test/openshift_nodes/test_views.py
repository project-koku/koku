#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
from django.db.models import F
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.provider.gcp.openshift.models import OCPGCPCostLineItemProjectDailySummaryP
from reporting.provider.ocp.models import OCPCostSummaryByNodeP

RBAC_NODE = "node_0"


class ResourceTypesViewTestOpenshiftNodes(IamTestCase):
    """Tests the resource types views."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()

    @RbacPermissions({"openshift.node": {"read": [RBAC_NODE]}})
    def test_openshift_node_with_node_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__in=[RBAC_NODE])
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-nodes")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}})
    def test_openshift_node_with_cluster_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(cluster_id__in=["OCP-on-AWS"])
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-nodes")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}, "openshift.node": {"read": [RBAC_NODE]}})
    def test_openshift_node_with_cluster_and_node_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__in=[RBAC_NODE], cluster_id__in=["OCP-on-AWS"])
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-nodes")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}, "openshift.node": {"read": ["*"]}})
    def test_openshift_node_with_cluster_and_all_node_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(cluster_id__in=["OCP-on-AWS"])
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-nodes")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.node": {"read": [RBAC_NODE]}})
    def test_openshift_node_with_all_cluster_and_node_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__in=[RBAC_NODE])
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-nodes")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    def test_openshift_node_with_aws_cloud_filter(self):
        """Test endpoint filters nodes to only those correlated with AWS."""
        with schema_context(self.schema_name):
            expected = (
                OCPAWSCostLineItemProjectDailySummaryP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__isnull=False)
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-nodes") + "?aws=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(json_result.get("meta", {}).get("count"), expected)

    def test_openshift_node_with_azure_cloud_filter(self):
        """Test endpoint filters nodes to only those correlated with Azure."""
        with schema_context(self.schema_name):
            expected = (
                OCPAzureCostLineItemProjectDailySummaryP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__isnull=False)
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-nodes") + "?azure=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(json_result.get("meta", {}).get("count"), expected)

    def test_openshift_node_with_gcp_cloud_filter(self):
        """Test endpoint filters nodes to only those correlated with GCP."""
        with schema_context(self.schema_name):
            expected = (
                OCPGCPCostLineItemProjectDailySummaryP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__isnull=False)
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-nodes") + "?gcp=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(json_result.get("meta", {}).get("count"), expected)

    def test_openshift_node_with_all_cloud_filter(self):
        """Test endpoint filters nodes to only those correlated with any cloud provider."""
        url = reverse("openshift-nodes") + "?all_cloud=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    def test_openshift_node_with_multiple_cloud_params_returns_400(self):
        """Test that supplying multiple cloud params returns a 400 error."""
        url = reverse("openshift-nodes") + "?aws=true&azure=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_openshift_node_cloud_filter_false_is_noop(self):
        """Test that passing gcp=false does not apply cloud filtering."""
        url = reverse("openshift-nodes") + "?gcp=false"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
