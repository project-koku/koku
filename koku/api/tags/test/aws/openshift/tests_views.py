#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCP-on-AWS tag view."""
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from reporting.models import OCPAWSTagsSummary


class OCPAWSTagsViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()

        self.test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
            {"value": "-10", "unit": "day", "resolution": "daily"},
            {"value": "-30", "unit": "day", "resolution": "daily"},
        ]

    def test_keys_only(self):
        """Test that tag key data is for the correct time queries."""
        for case in self.test_cases:
            url = reverse("openshift-aws-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": True,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()

            self.assertNotEqual(data.get("data"), [])
            self.assertTrue(isinstance(data.get("data"), list))

    def test_tags_queries(self):
        """Test that tag data is for the correct time queries."""
        for case in self.test_cases:
            url = reverse("openshift-aws-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": False,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()

            self.assertNotEqual(data.get("data"), [])
            self.assertTrue(isinstance(data.get("data"), list))

    def test_with_and_filter(self):
        """Test the filter[and:] param in the view."""
        url = reverse("openshift-aws-tags")
        client = APIClient()

        params = {
            "filter[resolution]": "daily",
            "filter[time_scope_value]": "-10",
            "filter[time_scope_units]": "day",
            "filter[and:account]": ["account1", "account2"],
        }
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()
        self.assertEqual(response_data.get("data", []), [])

    @RbacPermissions(
        {
            "aws.account": {"read": ["*"]},
            "openshift.cluster": {"read": ["*"]},
            "openshift.project": {"read": ["cost-management"]},
            "openshift.node": {"read": ["*"]},
        }
    )
    def test_rbac_tags_queries(self):
        """Test that appropriate tag values are returned when data is restricted by namespace."""
        cost_mgmt_tag_values = {
            "version": ["beta"],
            "storageclass": ["epsilon"],
            "environment": ["dev"],
            "app": ["cost"],
        }
        url = reverse("openshift-aws-tags")
        client = APIClient()
        params = {"key_only": False}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        for tag in data.get("data"):
            self.assertIn(tag.get("key"), cost_mgmt_tag_values.keys())
            self.assertEqual(tag.get("values"), cost_mgmt_tag_values.get(tag.get("key")))

    def test_cluster_filter(self):
        """Test that appropriate tag values are returned when data is filtered by cluster."""
        url = reverse("openshift-aws-tags")
        client = APIClient()
        params = {"key_only": False, "filter[enabled]": False, "filter[cluster]": "OCP-on-AWS"}
        url = url + "?" + urlencode(params, quote_via=quote_plus)
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        cluster_tags = (
            OCPAWSTagsSummary.objects.filter(report_period__cluster_id__contains="OCP-on-AWS")
            .values("key")
            .distinct()
            .all()
        )
        tag_keys = [tag.get("key") for tag in cluster_tags]
        for tag in data.get("data"):
            self.assertIn(tag.get("key"), tag_keys)
