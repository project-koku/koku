#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views."""
import logging
import random

from django.test import RequestFactory
from django.urls import reverse
from django_tenants.utils import tenant_context
from faker import Faker
from rest_framework import status
from rest_framework.test import APIClient

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

    def test_incorrect_query(self):
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                qs = "?foo="
                url = reverse(endpoint) + qs
                expected = "{'Unsupported parameter'}"
                response = self.client.get(url, **self.headers)
                result = str(response.data.get("foo")[0])
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(result, expected)


class ResourceTypesViewTest(IamTestCase):
    """Tests the resource types views."""

    ENDPOINTS_RTYPE = ["resource-types"]
    ENDPOINTS_AWS = [
        "aws-accounts",
        "aws-regions",
        "aws-services",
        "aws-organizational-units",
        "aws-categories",
        "aws-ec2-compute-instances",
        "aws-ec2-compute-os",
    ]
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

    @RbacPermissions({"aws.account": {"read": ["*"]}, "aws.organizational_unit": {"read": ["*"]}})
    def test_aws_endpoints_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS_AWS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"gcp.account": {"read": ["*"]}, "gcp.project": {"read": ["*"]}})
    def test_gcp_endpoints_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS_GCP:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions(
        {"openshift.cluster": {"read": ["*"]}, "openshift.project": {"read": ["*"]}, "openshift.node": {"read": ["*"]}}
    )
    def test_openshift_endpoints_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS_OPENSHIFT:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_accounts_ocp_view(self):
        """Test endpoint runs with a customer owner."""
        qs = "?openshift=true"
        url = reverse("aws-accounts") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_regions_ocp_view(self):
        """Test endpoint runs with openshift=true parameter."""
        qs = "?openshift=true"
        url = reverse("aws-regions") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_services_ocp_view(self):
        """Test endpoint runs with openshift=true parameter."""
        qs = "?openshift=true"
        url = reverse("aws-services") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"gcp.account": {"read": ["*"]}, "gcp.project": {"read": ["*"]}})
    def test_gcp_accounts_ocp_view(self):
        """Test endpoint runs with openshift=true parameter."""
        qs = "?openshift=true"
        url = reverse("gcp-accounts") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"gcp.account": {"read": ["*"]}, "gcp.project": {"read": ["*"]}})
    def test_gcp_regions_ocp_view(self):
        """Test endpoint runs with openshift=true parameter."""
        qs = "?openshift=true"
        url = reverse("gcp-regions") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"gcp.account": {"read": ["*"]}, "gcp.project": {"read": ["*"]}})
    def test_gcp_services_ocp_view(self):
        """Test endpoint runs with openshift=true parameter."""
        qs = "?openshift=true"
        url = reverse("gcp-services") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"azure.subscription_guid": {"read": ["*"]}})
    def test_azure_endpoints_view(self):
        """Test endpoint runs with a customer owner."""
        for endpoint in self.ENDPOINTS_AZURE:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"azure.subscription_guid": {"read": ["*"]}})
    def test_azure_subscriptions_guids_ocp_view(self):
        """Test endpoint runs with a customer owner."""
        qs = "?openshift=true"
        url = reverse("azure-subscription-guids") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"azure.subscription_guid": {"read": ["*"]}})
    def test_azure_regions_ocp_view(self):
        """Test endpoint runs with a customer owner."""
        qs = "?openshift=true"
        url = reverse("azure-regions") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"azure.subscription_guid": {"read": ["*"]}})
    def test_azure_services_ocp_view(self):
        """Test endpoint runs with a customer owner."""
        qs = "?openshift=true"
        url = reverse("azure-services") + qs
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

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

    def test_incorrect_query_all_endpoints(self):
        """Test invalid delta value."""
        self.ENDPOINTS = self.ENDPOINTS_AWS + self.ENDPOINTS_AZURE + self.ENDPOINTS_OPENSHIFT + self.ENDPOINTS_GCP
        # Tests all endpoints but the baseline resource-types
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                qs = "?foo="
                url = reverse(endpoint) + qs
                expected = "{'Unsupported parameter'}"
                response = self.client.get(url, **self.headers)
                result = str(response.data.get("foo")[0])
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(result, expected)

    def test_correct_search_all_endspoints(self):
        """Test invalid delta value."""
        self.ENDPOINTS = self.ENDPOINTS_AWS + self.ENDPOINTS_AZURE + self.ENDPOINTS_OPENSHIFT + self.ENDPOINTS_GCP
        # Tests all endpoints but the baseline resource-types for searching
        for endpoint in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                qs = "?search=foo"
                url = reverse(endpoint) + qs
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions({"aws.account": {"read": ["1234"]}, "aws.organizational_unit": {"read": ["1234"]}})
    def test_rbacpermissions_aws_account_data_returns_null(self):
        """Test that Aws endpoints accept valid Aws permissions."""
        for endpoint in self.ENDPOINTS_AWS:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertEqual(json_result.get("data"), [])

    @RbacPermissions({"azure.subscription_guid": {"read": ["1234"]}})
    def test_rbacpermissions_azure_account_data_returns_null(self):
        """Test that OpenShift endpoints accept valid OpenShift permissions."""
        for endpoint in self.ENDPOINTS_AZURE:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertEqual(json_result.get("data"), [])

    @RbacPermissions({"gcp.account": {"read": ["1234"]}, "gcp.project": {"read": ["1234"]}})
    def test_rbacpermissions_gcp_returns_empty_list(self):
        """Test that OpenShift endpoints accept valid OpenShift permissions."""
        for endpoint in self.ENDPOINTS_GCP:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertEqual(json_result.get("data"), [])

    @RbacPermissions(
        {
            "openshift.cluster": {"read": ["1234"]},
            "openshift.project": {"read": ["1234"]},
            "openshift.node": {"read": ["1234"]},
        }
    )
    def test_rbacpermissions_openshift_data_returns_empty_list(self):
        """Test that OpenShift endpoints accept valid OpenShift permissions."""
        for endpoint in self.ENDPOINTS_OPENSHIFT:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertEqual(json_result.get("data"), [])

    @RbacPermissions(
        {
            "openshift.not.cluster": {"read": ["1234"]},
            "openshift.not.project": {"read": ["1234"]},
            "openshift.not.node": {"read": ["1234"]},
        }
    )
    def test_wrong_rbacpermissions_openshift_data_returns_403(self):
        """Test that OpenShift endpoints accept valid OpenShift permissions."""
        for endpoint in self.ENDPOINTS_OPENSHIFT:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions({"openshift.project": {"read": ["1234"]}})
    def test_openshift_project_with_project_access_view(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("openshift-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"openshift.cluster": {"read": ["1234"]}})
    def test_openshift_project_with_cluster_access_view(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("openshift-projects")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)


class OCPGpuResourceTypesViewTest(IamTestCase):
    """Tests for OCP GPU resource types views (vendors and models). AI Generated Cursor Code."""

    ENDPOINTS_OCP_GPU = ["openshift-gpu-vendors", "openshift-gpu-models"]

    def setUp(self):
        """Set up the test case."""
        super().setUp()
        self.client = APIClient()
        self.factory = RequestFactory()

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.project": {"read": ["*"]}})
    def test_ocp_gpu_endpoints_view(self):
        """Test endpoint runs with wildcard access."""
        for endpoint in self.ENDPOINTS_OCP_GPU:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.project": {"read": ["*"]}})
    def test_ocp_gpu_endpoints_search(self):
        """Test search/type-ahead functionality for GPU endpoints."""
        for endpoint in self.ENDPOINTS_OCP_GPU:
            with self.subTest(endpoint=endpoint):
                qs = "?search=test"
                url = reverse(endpoint) + qs
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.project": {"read": ["*"]}})
    def test_ocp_gpu_endpoints_incorrect_query(self):
        """Test invalid query parameter handling for GPU endpoints."""
        for endpoint in self.ENDPOINTS_OCP_GPU:
            with self.subTest(endpoint=endpoint):
                qs = "?foo="
                url = reverse(endpoint) + qs
                expected = "{'Unsupported parameter'}"
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                result = str(response.data.get("foo")[0])
                self.assertEqual(result, expected)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.project": {"read": ["*"]}})
    def test_ocp_gpu_endpoints_filter_by_namespace(self):
        """Test filtering by namespace query parameter."""
        for endpoint in self.ENDPOINTS_OCP_GPU:
            with self.subTest(endpoint=endpoint):
                qs = "?namespace=test-namespace"
                url = reverse(endpoint) + qs
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.project": {"read": ["*"]}})
    def test_ocp_gpu_endpoints_filter_by_cluster_id(self):
        """Test filtering by cluster_id query parameter."""
        for endpoint in self.ENDPOINTS_OCP_GPU:
            with self.subTest(endpoint=endpoint):
                qs = "?cluster_id=test-cluster"
                url = reverse(endpoint) + qs
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"openshift.cluster": {"read": ["1234"]}, "openshift.project": {"read": ["1234"]}})
    def test_ocp_gpu_endpoints_rbac_specific_access_returns_empty(self):
        """Test that specific RBAC permissions return empty list when no matching data."""
        for endpoint in self.ENDPOINTS_OCP_GPU:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                json_result = response.json()
                self.assertIsNotNone(json_result.get("data"))
                self.assertIsInstance(json_result.get("data"), list)
                self.assertEqual(json_result.get("data"), [])

    @RbacPermissions({"openshift.project": {"read": ["*"]}})
    def test_ocp_gpu_vendors_with_project_access_view(self):
        """Test GPU vendors endpoint runs with project access."""
        url = reverse("openshift-gpu-vendors")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}})
    def test_ocp_gpu_models_with_cluster_access_view(self):
        """Test GPU models endpoint runs with cluster access."""
        url = reverse("openshift-gpu-models")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)

    @RbacPermissions(
        {
            "openshift.not.cluster": {"read": ["1234"]},
            "openshift.not.project": {"read": ["1234"]},
        }
    )
    def test_wrong_rbacpermissions_ocp_gpu_returns_403(self):
        """Test that GPU endpoints return 403 with wrong permissions."""
        for endpoint in self.ENDPOINTS_OCP_GPU:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
