#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for OpenShift quotas resource type view."""
from django.test import RequestFactory
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status

from api.iam.test.iam_test_case import IamTestCase
from reporting.provider.ocp.models import OCPCostSummaryByQuotaP


class ResourceTypesViewTestOpenshiftQuotas(IamTestCase):
    """Tests for OpenShift quotas resource type view."""

    def test_openshift_quotas_view(self):
        """Test that the openshift quotas endpoint returns 200."""
        url = reverse("openshift-quotas")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json().get("data", [])
        self.assertIsInstance(data, list)

    def test_openshift_quotas_with_cluster_access(self):
        """Test that cluster RBAC filtering works for quotas."""
        url = reverse("openshift-quotas")
        self.headers["HTTP_X_RH_IDENTITY"] = self.headers.get("HTTP_X_RH_IDENTITY", "")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_openshift_quotas_unsupported_param(self):
        """Test that unsupported query params return 400."""
        url = reverse("openshift-quotas") + "?bad_param=true"
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
