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
"""Test the Navigation view."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions


class NavigationViewTest(IamTestCase):
    """Tests the resource types views."""

    def setUp(self):
        """Set up the Navigation view tests."""
        super().setUp()
        self.client = APIClient()

    @RbacPermissions({"aws.account": {"read": ["*"]}})
    def test_aws_view_read(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": True} in response.data.get("data"))
        self.assertTrue({"ocp": False} in response.data.get("data"))
        self.assertTrue({"gcp": False} in response.data.get("data"))

    @RbacPermissions({"aws.account": "*"})
    def test_aws_view_wildcard(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": True} in response.data.get("data"))
        self.assertTrue({"ocp": False} in response.data.get("data"))
        self.assertTrue({"gcp": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "openshift.cluster": {"read": ["*"]},
            "openshift.project": {"read": ["myproject"]},
            "openshift.node": {"read": ["mynode"]},
        }
    )
    def test_ocp_view_cluster(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": True} in response.data.get("data"))
        self.assertTrue({"gcp": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "openshift.cluster": {"read": ["mycluster"]},
            "openshift.project": {"read": ["*"]},
            "openshift.node": {"read": ["mynode"]},
        }
    )
    def test_ocp_view_project(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": True} in response.data.get("data"))
        self.assertTrue({"gcp": False} in response.data.get("data"))

    @RbacPermissions(
        {
            "openshift.cluster": {"read": ["mycluster"]},
            "openshift.project": {"read": ["myproject"]},
            "openshift.node": {"read": ["*"]},
        }
    )
    def test_ocp_view_node(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": True} in response.data.get("data"))
        self.assertTrue({"gcp": False} in response.data.get("data"))

    @RbacPermissions({"openshift.cluster": "*"})
    def test_ocp_view_cluster_wildcard(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": True} in response.data.get("data"))
        self.assertTrue({"gcp": False} in response.data.get("data"))

    @RbacPermissions({"openshift.project": "*"})
    def test_ocp_view_project_wildcard(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": True} in response.data.get("data"))
        self.assertTrue({"gcp": False} in response.data.get("data"))

    @RbacPermissions({"openshift.node": "*"})
    def test_ocp_view_node_wildcard(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": True} in response.data.get("data"))
        self.assertTrue({"gcp": False} in response.data.get("data"))

    @RbacPermissions({"gcp.account": {"read": ["*"]}, "gcp.project": {"read": ["myproject"]}})
    def test_gcp_view_account(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": False} in response.data.get("data"))
        self.assertTrue({"gcp": True} in response.data.get("data"))

    @RbacPermissions({"gcp.account": {"read": ["myaccount"]}, "gcp.project": {"read": ["*"]}})
    def test_gcp_view_project(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": False} in response.data.get("data"))
        self.assertTrue({"gcp": True} in response.data.get("data"))

    @RbacPermissions({"gcp.account": "*"})
    def test_gcp_view_account_wildcard(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": False} in response.data.get("data"))
        self.assertTrue({"gcp": True} in response.data.get("data"))

    @RbacPermissions({"gcp.project": "*"})
    def test_gcp_view_project_wildcard(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")

        response = self.client.get(url, **self.headers)

        self.assertEqual(len(response.data.get("data")), 3)
        self.assertTrue({"aws": False} in response.data.get("data"))
        self.assertTrue({"ocp": False} in response.data.get("data"))
        self.assertTrue({"gcp": True} in response.data.get("data"))

    @RbacPermissions({"aws.account": "*"})
    def test_aws_view_query_read(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        query_url = f"{url}?source_type=aws"
        response = self.client.get(query_url, **self.headers)

        self.assertTrue(response.data.get("data"))

    @RbacPermissions({"openshift.cluster": "*"})
    def test_openshift_view_query_read_for_aws(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        query_url = f"{url}?source_type=aws"
        response = self.client.get(query_url, **self.headers)

        self.assertFalse(response.data.get("data"))

    def test_view_query_invalid_source_type(self):
        """Test endpoint runs with a customer owner."""
        url = reverse("navigation")
        query_url = f"{url}?source_type=bad"
        response = self.client.get(query_url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
