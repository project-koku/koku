#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Resource Types views for OpenShift Virtual Machines."""
from django.db.models import F
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.iam.test.iam_test_case import RbacPermissions
from api.report.test.util.constants import OCP_NAMESPACES
from reporting.provider.ocp.models import OCPVirtualMachineSummaryP

RBAC_PROJECT = OCP_NAMESPACES[0]


class ResourceTypesViewTestOpenshiftVirtualMachines(IamTestCase):
    """Tests the resource types views for OpenShift virtual machines."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.client = APIClient()

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}})
    def test_openshift_virtual_machines_with_cluster_access_view(self):
        """Test endpoint runs with a customer owner."""

        with schema_context(self.schema_name):
            expected = (
                OCPVirtualMachineSummaryP.objects.annotate(**{"value": F("vm_name")})
                .values("value")
                .distinct()
                .filter(cluster_id__in=["OCP-on-AWS"])
                .count()
            )

        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-virtual-machines")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}, "openshift.project": {"read": [RBAC_PROJECT]}})
    def test_openshift_project_with_cluster_and_project_access_view(self):
        """Test endpoint runs with a customer owner."""

        with schema_context(self.schema_name):
            expected = (
                OCPVirtualMachineSummaryP.objects.annotate(**{"value": F("namespace")})
                .values("value")
                .distinct()
                .filter(namespace__in=[RBAC_PROJECT], cluster_id__in=["OCP-on-AWS"])
                .count()
            )

        # check that the expected is not zero
        self.assertTrue(expected)

        url = reverse("openshift-virtual-machines")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["OCP-on-AWS"]}, "openshift.project": {"read": ["*"]}})
    def test_openshift_project_with_cluster_and_all_project_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPVirtualMachineSummaryP.objects.annotate(**{"value": F("namespace")})
                .values("value")
                .distinct()
                .filter(cluster_id__in=["OCP-on-AWS"])
                .count()
            )
        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-virtual-machines")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}, "openshift.project": {"read": [RBAC_PROJECT]}})
    def test_openshift_project_with_all_cluster_and_project_access_view(self):
        """Test endpoint runs with a customer owner."""
        with schema_context(self.schema_name):
            expected = (
                OCPVirtualMachineSummaryP.objects.annotate(**{"value": F("namespace")})
                .values("value")
                .distinct()
                .filter(namespace__in=[RBAC_PROJECT])
                .count()
            )

        # check that the expected is not zero
        self.assertTrue(expected)
        url = reverse("openshift-virtual-machines")
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        self.assertIsNotNone(json_result.get("data"))
        self.assertIsInstance(json_result.get("data"), list)
        self.assertEqual(len(json_result.get("data")), expected)

    @RbacPermissions({"openshift.cluster": {"read": ["*"]}})
    def test_openshift_virtual_machines_query_filter_keys(self):
        """Test that endpoint filters results correctly based on query parameters."""

        query_filter_keys = {"cluster_id", "cluster_alias", "namespace", "node"}

        for key in query_filter_keys:
            with self.subTest(param=key):
                with schema_context(self.schema_name):
                    values = OCPVirtualMachineSummaryP.objects.values_list(key, flat=True).distinct()
                    self.assertTrue(values.exists())
                    test_value = values.first()

                    expected = (
                        OCPVirtualMachineSummaryP.objects.annotate(value=F("vm_name"))
                        .values("value")
                        .distinct()
                        .filter(**{f"{key}__icontains": test_value})
                        .count()
                    )

                self.assertTrue(expected)

                url = reverse("openshift-virtual-machines")
                params = {key: test_value}
                response = self.client.get(url, params, **self.headers)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

                json_result = response.json()
                self.assertEqual(len(json_result.get("data")), expected)

    def test_openshift_virtual_machines_with_unsupported_query_param(self):
        """Test view returns error for unsupported query parameter."""

        url = reverse("openshift-virtual-machines")
        params = {"unsupported_param": "unsupported-param"}
        response = self.client.get(url, params, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
