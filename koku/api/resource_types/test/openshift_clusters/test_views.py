#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
from django.db.models import F
from django.db.models.functions.comparison import Coalesce
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryP
from reporting.provider.azure.openshift.models import OCPAzureCostSummaryP
from reporting.provider.gcp.openshift.models import OCPGCPCostSummaryP
from reporting.provider.ocp.models import OCPCostSummaryP


class ResourceTypesViewTestOpenshiftClusters(IamTestCase):
    """Tests the resource types views."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}})
    def test_openshift_cluster_with_cluster_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPCostSummaryP.objects.annotate(
                    **{"value": F("cluster_id"), "ocp_cluster_alias": Coalesce(F("cluster_alias"), "cluster_id")}
                )
                .values("value", "ocp_cluster_alias")
                .distinct()
                .filter(cluster_id__in=["OCP-on-AWS"])
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-clusters")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    def test_openshift_cluster_with_aws_cloud_filter(self):
        """Test endpoint filters clusters to only those correlated with AWS."""
        with schema_context(self.schema_name):
            expected = (
                OCPAWSCostSummaryP.objects.annotate(
                    **{"value": F("cluster_id"), "ocp_cluster_alias": Coalesce(F("cluster_alias"), "cluster_id")}
                )
                .values("value", "ocp_cluster_alias")
                .distinct()
                .filter(cluster_id__isnull=False)
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-clusters") + "?aws=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(json_result.get("meta", {}).get("count"), expected)

    def test_openshift_cluster_with_azure_cloud_filter(self):
        """Test endpoint filters clusters to only those correlated with Azure."""
        with schema_context(self.schema_name):
            expected = (
                OCPAzureCostSummaryP.objects.annotate(
                    **{"value": F("cluster_id"), "ocp_cluster_alias": Coalesce(F("cluster_alias"), "cluster_id")}
                )
                .values("value", "ocp_cluster_alias")
                .distinct()
                .filter(cluster_id__isnull=False)
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-clusters") + "?azure=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(json_result.get("meta", {}).get("count"), expected)

    def test_openshift_cluster_with_gcp_cloud_filter(self):
        """Test endpoint filters clusters to only those correlated with GCP."""
        with schema_context(self.schema_name):
            expected = (
                OCPGCPCostSummaryP.objects.annotate(
                    **{"value": F("cluster_id"), "ocp_cluster_alias": Coalesce(F("cluster_alias"), "cluster_id")}
                )
                .values("value", "ocp_cluster_alias")
                .distinct()
                .filter(cluster_id__isnull=False)
                .count()
            )
        self.assertTrue(expected)
        url = reverse("openshift-clusters") + "?gcp=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(json_result.get("meta", {}).get("count"), expected)

    def test_openshift_cluster_with_all_cloud_filter(self):
        """Test endpoint filters clusters to only those correlated with any cloud provider."""
        url = reverse("openshift-clusters") + "?all_cloud=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    def test_openshift_cluster_with_multiple_cloud_params_returns_400(self):
        """Test that supplying multiple cloud params returns a 400 error."""
        url = reverse("openshift-clusters") + "?aws=true&gcp=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_openshift_cluster_cloud_filter_false_is_noop(self):
        """Test that passing azure=false does not apply cloud filtering."""
        url = reverse("openshift-clusters") + "?azure=false"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
