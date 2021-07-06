#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
import logging
import random

from django.test import RequestFactory
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from masu.test import MasuTestCase

FAKE = Faker()


class CostModelResourseTypesTest(MasuTestCase):
    """Test cases for the cost model resource type endpoint."""

    ENDPOINTS = ["cost-models"]

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        # Must set this to capture the logger messages in the tests.
        logging.disable(0)

    def setUp(self):
        """Set up the shared variables for each test case."""
        super().setUp()
        with tenant_context(self.tenant):
            self.cost_model = CostModel.objects.create(
                name=FAKE.word(), description=FAKE.word(), source_type=random.choice(Provider.PROVIDER_CHOICES)
            )
            self.cost_model_map = CostModelMap.objects.create(
                cost_model=self.cost_model, provider_uuid=self.aws_provider_uuid
            )

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


class ResourceTypesViewTest(IamTestCase):
    """Tests the resource types views."""

    ENDPOINTS_RTYPE = ["resource-types"]
    ENDPOINTS_AWS = ["aws-accounts", "aws-regions", "aws-services", "aws-organizational-units"]
    ENDPOINTS_GCP = ["gcp-accounts", "gcp-projects", "gcp-regions", "gcp-services"]
    ENDPOINTS_AZURE = ["azure-subscription-guids", "azure-services", "azure-regions"]
    ENDPOINTS_OPENSHIFT = ["openshift-clusters", "openshift-nodes", "openshift-projects"]
    ENDPOINTS = ENDPOINTS_RTYPE + ENDPOINTS_AWS + ENDPOINTS_AZURE + ENDPOINTS_OPENSHIFT + ENDPOINTS_GCP

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

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_account_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("aws-accounts")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.organizational_unit": {"read": ["*"]}})
    def test_aws_organizational_unit_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("aws-organizational-units")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_service_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("aws-services")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_region_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("aws-regions")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"azure.subscription_guid": {"read": ["*"]}})
    def test_azure_subscription_guid__view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("azure-subscription-guids")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"gcp.account": {"read": ["*"]}})
    def test_gcp_account_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("gcp-accounts")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"gcp.project": {"read": ["*"]}})
    def test_gcp_project_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("gcp-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}})
    def test_openshift_cluster_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("openshift-clusters")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"openshift.node": {"read": ["*"]}})
    def test_openshift_node_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("openshift-nodes")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"openshift.project": {"read": ["*"]}})
    def test_openshift_project_view(self):
        """Test that getting a forecast with limited access returns valid result."""
        url = reverse("openshift-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.organizational_unit": {"read": ["OU_001"]}})
    def test_rbacpermissions_aws_org_unit_data(self):
        """Test that OpenShift endpoints accept valid OpenShift permissions."""
        url = reverse("aws-organizational-units")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertTrue(len(json_result.get("data")) > 0)

    @RbacPermissions({"aws.account": {"read": ["1234", "6789"]}})
    def test_rbacpermissions_aws_account_data(self):
        """Test that OpenShift endpoints accept valid OpenShift permissions."""
        url = reverse("aws-accounts")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(json_result.get("data"), [])
