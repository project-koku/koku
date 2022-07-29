#
# Copyright 2022 Red Hat Inc.
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
from reporting.provider.oci.models import OCICostSummaryByAccountP


class ResourceTypesViewTestOCITenants(IamTestCase):
    """Tests the resource types views."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()

    @RbacPermissions({"oci.payer_tenant_id": {"read": ["*"]}})
    def test_oci_tenant_with_tenant_access_wildcard_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCICostSummaryByAccountP.objects.annotate(**{"value": F("payer_tenant_id")})
                .values("value")
                .distinct()
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("oci-payer-tenant-ids")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"oci.payer_tenant_id": {"read": ["8d361f2b-f1ff-4718-8159-181db259f6c9"]}})
    def test_oci_tenant_with_tenant_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCICostSummaryByAccountP.objects.annotate(**{"value": F("payer_tenant_id")})
                .values("value")
                .distinct()
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("oci-payer-tenant-ids")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"oci.payer_tenant_id": {"read": ["*"]}})
    def test_oci_tenant_with_tenant_access_view_bad_request(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCICostSummaryByAccountP.objects.annotate(**{"value": F("payer_tenant_id")})
                .values("value")
                .distinct()
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = "%s?invalid=parameter" % reverse("oci-payer-tenant-ids")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
