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
from reporting.provider.aws.openshift.models import OCPAWSCostLineItemDailySummary
from reporting.provider.azure.openshift.models import OCPAzureCostLineItemDailySummary
from reporting.provider.ocp.models import OCPCostSummaryByNodeP


class ResourceTypesViewTestOpenshiftNodes(IamTestCase):
    """Tests the resource types views."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()

    @RbacPermissions({"openshift.node": {"read": ["aws_compute_1"]}})
    def test_openshift_node_with_node_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__in=["aws_compute_1"])
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

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}, "openshift.node": {"read": ["aws_compute_1"]}})
    def test_openshift_node_with_cluster_and_node_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__in=["aws_compute_1"], cluster_id__in=["OCP-on-AWS"])
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

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.node": {"read": ["aws_compute_1"]}})
    def test_openshift_node_with_all_cluster_and_node_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryByNodeP.objects.annotate(**{"value": F("node")})
                .values("value")
                .distinct()
                .filter(node__in=["aws_compute_1"])
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

    def test_openshift_nodes_on_cloud_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                (
                    OCPAWSCostLineItemDailySummary.objects.annotate(**{"value": F("node")})
                    .values("value")
                    .distinct()
                    .filter(node__isnull=False)
                )
                .union(
                    (
                        OCPAzureCostLineItemDailySummary.objects.annotate(**{"value": F("node")})
                        .values("value")
                        .distinct()
                        .filter(node__isnull=False)
                    ),
                    all=True,
                )
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        qs = "?cloud=true&limit=200"
        url = reverse("openshift-nodes") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)
