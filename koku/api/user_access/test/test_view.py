#
# Copyright 2021 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the UserAccess view."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions


class UserAccessViewTest(IamTestCase):
    """Tests the resource types views."""

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
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": ["123"]},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": ["*"]},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": ["*"]},
            "gcp.project": {"read": ["myproject"]},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": ["myaccount"]},
            "gcp.project": {"read": ["*"]},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": ["*"]},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": ["*"]},
            "azure.subscription_guid": {"read": []},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": ["*"]},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "aws.account": {"read": []},
            "aws.organizational_unit": {"read": []},
            "gcp.account": {"read": []},
            "gcp.project": {"read": []},
            "azure.subscription_guid": {"read": ["*"]},
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

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": False} in response.data.get("data"))
        self.assertTrue({"type": "azure", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "cost_model", "access": False} in response.data.get("data"))

    def test_view_as_org_admin(self):
        """Test user-access view as an org admin."""
        url = reverse("user-access")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 5)
        self.assertTrue({"type": "aws", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "ocp", "access": True} in response.data.get("data"))
        self.assertTrue({"type": "gcp", "access": True} in response.data.get("data"))
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
            "azure.subscription_guid": {"read": []},
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
            "azure.subscription_guid": {"read": []},
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
            "azure.subscription_guid": {"read": []},
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
            "azure.subscription_guid": {"read": []},
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
