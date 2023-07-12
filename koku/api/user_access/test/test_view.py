#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the UserAccess view."""
from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions


class UserAccessViewTest(IamTestCase):
    """Tests the resource types views."""

    NUM_ACCESS_CLASSES = 9

    def setUp(self):
        """Set up the UserAccess view tests."""
        super().setUp()
        self.client = APIClient()

    @RbacPermissions(
        {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_aws_view_read(self):
        """Test user-access view with aws read wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": ["123"]},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_aws_view_read_specific_account(self):
        """Test user-access view with aws read specific account permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_aws_view_wildcard(self):
        """Test user-access view with aws wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": ["*"]},
            "openshift.node": {"read": ["mynode"]},
            "openshift.project": {"read": ["myproject"]},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_ocp_view_cluster(self):
        """Test user-access view with openshift cluster read wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": ["mycluster"]},
            "openshift.node": {"read": ["mynode"]},
            "openshift.project": {"read": ["*"]},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_ocp_view_project(self):
        """Test user-access view with openshift project read wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": ["mycluster"]},
            "openshift.node": {"read": ["*"]},
            "openshift.project": {"read": ["myproject"]},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_ocp_view_node(self):
        """Test user-access view with openshift node read wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": ["*"]},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_ocp_view_cluster_wildcard(self):
        """Test user-access view with openshift cluster wildcard permission."""
        url = reverse("user-access")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": [""]},
            "openshift.node": {"read": []},
            "openshift.project": {"read": ["*"]},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_ocp_view_project_wildcard(self):
        """Test user-access view with openshift project wildcard permission."""
        url = reverse("user-access")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": ["*"]},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_ocp_view_node_wildcard(self):
        """Test user-access view with openshift node wildcard permission."""
        url = reverse("user-access")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": ["*"]},
            "gcp.project": {"read": ["myproject"]},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_gcp_view_account(self):
        """Test user-access view with gcp account read wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": ["myaccount"]},
            "gcp.project": {"read": ["*"]},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_gcp_view_project(self):
        """Test user-access view with gcp project read wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": ["*"]},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_gcp_view_account_wildcard(self):
        """Test user-access view with gcp account wildcard permission."""
        url = reverse("user-access")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": ["*"]},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_gcp_view_project_wildcard(self):
        """Test user-access view with gcp project wildcard permission."""
        url = reverse("user-access")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": ["*"]},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    @override_settings(ENABLE_PRERELEASE_FEATURES=True)
    def test_ibm_view_account_wildcard_with_pre_release_features(self):
        """Test user-access view with ibm account read wildcard permission and pre_release env=true."""
        url = reverse("user-access")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": ["*"]},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    @override_settings(ENABLE_PRERELEASE_FEATURES=False)
    def test_ibm_view_account_wildcard_with_pre_release_features_false(self):
        """Test user-access view with ibm account read wildcard permission and pre_release env=false."""
        url = reverse("user-access")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": ["*"]},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_azure_view_read(self):
        """Test user-access view with azure subscription read wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": ["*"]},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_azure_view_wildcard(self):
        """Test user-access view with azure subscription wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": ["*"]},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_oci_view_wildcard(self):
        """Test user-access view with oci tenant wildcard permission."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions({})
    def test_view_no_access(self):
        """Test user-access view as an org admin."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @override_settings(ENABLE_PRERELEASE_FEATURES=False)
    def test_view_as_org_admin_prerelease_features_off(self):
        """Test user-access view as an org admin."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))

        # IBM is a pre-release feature
        self.assertTrue({"type": "ibm", "access": False} in response.data.get("data"))

        self.assertTrue({"type": "azure", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": True} in response.data.get("data"))

    @override_settings(ENABLE_PRERELEASE_FEATURES=True)
    def test_view_as_org_admin_prerelease_features_on(self):
        """Test user-access view as an org admin."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), self.NUM_ACCESS_CLASSES)
        self.assertTrue({"type": "any", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "oci", "access": True} in response.data.get("data"))

        # IBM is a pre-release feature
        self.assertTrue({"type": "ibm", "access": True} in response.data.get("data"))

        self.assertTrue({"type": "azure", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": True} in response.data.get("data"))

    def test_aws_view_query_read_org_admin(self):
        """Test user-access view query as an org admin."""
        url = reverse("user-access")
        query_url = f"{url}?source_type=aws"
        response = self.client.get(query_url, **self.headers)

        self.assertTrue(response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": []},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_aws_view_query_read(self):
        """Test user-access view query for aws."""
        url = reverse("user-access")
        query_url = f"{url}?source_type=aws"
        response = self.client.get(query_url, **self.headers)

        self.assertTrue(response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": ["*"]},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": []},
        }
    )
    def test_openshift_view_query_read_for_aws(self):
        """Test user-access view query for aws with openshift permissions."""
        url = reverse("user-access")
        query_url = f"{url}?type=aws"
        response = self.client.get(query_url, **self.headers)

        self.assertFalse(response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": ["*"]},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": ["*"], "write": []},
        }
    )
    def test_cost_model_view_query_read_for_aws(self):
        """Test user-access view query for cost_model."""
        url = reverse("user-access")
        query_url = f"{url}?type=cost_model"
        response = self.client.get(query_url, **self.headers)

        self.assertTrue(response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "ibm.account": {"read": []},
            "azure.subscription_guid": {"read": []},
            "oci.payer_tenant_id": {"read": []},
            "openshift.cluster": {"read": ["*"]},
            "openshift.node": {"read": []},
            "openshift.project": {"read": []},
            "cost_model": {"read": [], "write": ["*"]},
        }
    )
    def test_cost_model_view_query_write_for_aws(self):
        """Test user-access view query for cost_model with write access."""
        url = reverse("user-access")
        query_url = f"{url}?type=cost_model"
        response = self.client.get(query_url, **self.headers)

        self.assertTrue(response.data.get("data"))

    def test_view_query_invalid_source_type(self):
        """Test user-access view query for invalid type."""
        url = reverse("user-access")
        query_url = f"{url}?type=bad"
        response = self.client.get(query_url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_view_beta_flag_true(self):
        """Test user-access view query using beta flag.

        Scenarios:
            pre-release features: allowed
            user access: allowed
            beta flag: true or false

        Expected:
            beta true result: true
            beta false result: true
        """
        url = reverse("user-access")

        for flag, expected in [(True, False), (False, True)]:
            with self.subTest(flag=flag, expected=expected):
                query_url = f"{url}?type=aws&beta={flag}"
                response = self.client.get(query_url, **self.headers)
                self.assertEqual(response.data.get("data"), expected)

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_view_beta_flag_false(self):
        """Test user-access view query using beta flag.

        Scenarios:
            pre-release features: disallowed
            user access: allowed
            beta flag: true or false

        Expected:
            beta true result: false
            beta false result: true
        """
        url = reverse("user-access")

        for flag, expected in [(True, False), (False, True)]:
            with self.subTest(flag=flag, expected=expected):
                query_url = f"{url}?type=aws&beta={flag}"
                response = self.client.get(query_url, **self.headers)
                self.assertEqual(response.data.get("data"), expected)

    @RbacPermissions({"something.else": {"read": ["*"]}})
    def test_view_beta_flag_true_unauth(self):
        """Test user-access view query using beta flag.

        Scenarios:
            pre-release features: allowed
            user access: disallowed
            beta flag: true or false

        Expected:
            beta true result: false
            beta false result: false
        """
        url = reverse("user-access")

        for flag, expected in [(True, False), (False, False)]:
            with self.subTest(flag=flag, expected=expected):
                query_url = f"{url}?type=aws&beta={flag}"
                response = self.client.get(query_url, **self.headers)
                self.assertEqual(response.data.get("data"), expected)

    @RbacPermissions({"something.else": {"read": ["*"]}})
    def test_view_beta_flag_false_unauth(self):
        """Test user-access view query using beta flag.

        Scenarios:
            pre-release features: disallowed
            user access: disallowed
            beta flag: true or false

        Expected:
            beta true result: false
            beta false result: false
        """
        url = reverse("user-access")

        for flag, expected in [(True, False), (False, False)]:
            with self.subTest(flag=flag, expected=expected):
                query_url = f"{url}?type=aws&beta={flag}"
                response = self.client.get(query_url, **self.headers)
                self.assertEqual(response.data.get("data"), expected)
