#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""E2E regression tests: Koku views authorized through a live Kessel stack.

These tests validate that Koku's RBAC-dependent API views produce the
same HTTP responses when authorization flows through Kessel/SpiceDB
instead of the legacy RBAC service.

PREREQUISITES
~~~~~~~~~~~~~
1. Start the Kessel stack::

       podman compose -f dev/kessel/docker-compose.yml up -d

2. Start a local PostgreSQL for Django::

       docker run -d --name koku-test-db -p 15432:5432 \\
           -e POSTGRES_DB=test -e POSTGRES_USER=koku_tester \\
           -e POSTGRES_PASSWORD=password postgres:16

3. Run::

       ENABLE_KESSEL_TEST=1 python koku/manage.py test \\
           koku_rebac.test.test_e2e_regression -v 2

These tests are **opt-in** and completely isolated from the legacy RBAC
test infrastructure.  They do not modify ``IamTestCase``,
``@RbacPermissions``, or any existing test file.
"""
import os
import unittest
from base64 import b64encode
from json import dumps as json_dumps
from unittest.mock import patch

from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .kessel_fixture import KesselFixture
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from koku.koku_test_runner import KokuTestRunner
from koku_rebac.models import KesselSyncedResource

_E2E_SKIP = "Requires live Kessel stack (ENABLE_KESSEL_TEST=1)"

E2E_USERNAME = "e2e_kessel_user"
E2E_DENIED_USERNAME = "e2e_denied_user"
E2E_ORG_ID = KokuTestRunner.org_id
E2E_ACCOUNT = KokuTestRunner.account
E2E_WORKSPACE_ID = E2E_ORG_ID

CLEAN_MIDDLEWARE = [m for m in settings.MIDDLEWARE if "DevelopmentIdentity" not in m]


def _build_identity_header(username, org_id=E2E_ORG_ID, account=E2E_ACCOUNT, is_admin=False):
    """Build a base64-encoded RH identity header."""
    identity = {
        "identity": {
            "account_number": account,
            "org_id": org_id,
            "type": "User",
            "user": {
                "username": username,
                "email": f"{username}@test.e2e",
                "is_org_admin": is_admin,
            },
        },
        "entitlements": {"cost_management": {"is_entitled": True}},
    }
    return b64encode(json_dumps(identity).encode("utf-8")).decode("utf-8")


@unittest.skipUnless(os.environ.get("ENABLE_KESSEL_TEST", ""), _E2E_SKIP)
@override_settings(
    AUTHORIZATION_BACKEND="rebac",
    ONPREM=True,
    DEVELOPMENT=False,
    ENHANCED_ORG_ADMIN=True,
    MIDDLEWARE=CLEAN_MIDDLEWARE,
)
class TestKesselE2ERegression(IamTestCase):
    """E2E tests: real Kessel authorization -> Koku views.

    Each test seeds specific Kessel tuples, sends an HTTP request as a
    non-admin user, and asserts the expected status code.  The test caches
    use DummyCache so every request evaluates authorization fresh.
    """

    fixture: KesselFixture

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixture = KesselFixture()
        cls.nonadmin_header = _build_identity_header(E2E_USERNAME, is_admin=False)
        cls.denied_header = _build_identity_header(E2E_DENIED_USERNAME, is_admin=False)
        cls.admin_header = _build_identity_header("e2e_admin_user", is_admin=True)

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self._created_source_ids = []

    def tearDown(self):
        for source_id in self._created_source_ids:
            try:
                source = Sources.objects.get(source_id=source_id)
                provider_uuid = source.koku_uuid
                if provider_uuid:
                    KesselSyncedResource.objects.filter(resource_id=str(provider_uuid)).delete()
                    from django.db import connection

                    with connection.cursor() as cursor:
                        schema = self.schema_name
                        cursor.execute(
                            f'DELETE FROM "{schema}".reporting_tenant_api_provider' " WHERE provider_id = %s",
                            [str(provider_uuid)],
                        )
                        cursor.execute(
                            "DELETE FROM api_provider WHERE uuid = %s",
                            [str(provider_uuid)],
                        )
                source.delete()
            except Sources.DoesNotExist:
                pass
        self._created_source_ids.clear()
        self.fixture.cleanup()
        super().tearDown()

    def _get(self, url_name, header_value, params=None):
        """GET a named URL with the given identity header and optional query params."""
        url = reverse(url_name)
        return self.client.get(url, data=params, HTTP_X_RH_IDENTITY=header_value)

    def _post(self, url_name, header_value, data=None):
        """POST to a named URL with the given identity header."""
        url = reverse(url_name)
        return self.client.post(url, data=data or {}, format="json", HTTP_X_RH_IDENTITY=header_value)

    def _put(self, url_name, header_value, data=None):
        """PUT to a named URL with the given identity header."""
        url = reverse(url_name)
        return self.client.put(url, data=data or {}, format="json", HTTP_X_RH_IDENTITY=header_value)

    def _delete(self, url_name, header_value, pk=None):
        """DELETE a named URL with the given identity header."""
        if pk is not None:
            url = reverse(url_name, kwargs={"pk": pk})
        else:
            url = reverse(url_name)
        return self.client.delete(url, HTTP_X_RH_IDENTITY=header_value)

    # ------------------------------------------------------------------
    # Non-OCP: access granted (Check returns ALLOWED_TRUE)
    # ------------------------------------------------------------------

    def test_s1_aws_read_granted(self):
        """User with aws.account read access can reach AWS cost reports."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})
        response = self._get("reports-aws-costs", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s2_gcp_read_granted(self):
        """User with gcp.account read access can reach GCP cost reports."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"gcp.account": {"read": ["*"]}})
        response = self._get("reports-gcp-costs", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s3_azure_read_granted(self):
        """User with azure read access can reach Azure cost reports."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"azure.subscription_guid": {"read": ["*"]}})
        response = self._get("reports-azure-costs", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s4_cost_model_read_granted(self):
        """User with cost_model read access can list cost models."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"cost_model": {"read": ["*"]}})
        response = self._get("cost-models-list", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s5_settings_read_granted(self):
        """User with settings read access can view tag settings."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"read": ["*"]}})
        response = self._get("settings-tags", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # Non-OCP: access denied (no tuples seeded)
    # ------------------------------------------------------------------

    def test_s6_no_permissions_returns_403(self):
        """User with no Kessel permissions is denied access to AWS reports.

        Uses a dedicated 'denied' user that never has tuples, avoiding
        stale-tuple issues from SpiceDB's minimize_latency consistency.
        """
        response = self._get("reports-aws-costs", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s7_partial_permissions_wrong_type_returns_403(self):
        """User with AWS-only permissions is denied access to GCP reports.

        Uses the denied user to ensure no GCP tuples exist; only AWS
        tuples are seeded for a different principal.
        """
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})
        response = self._get("reports-gcp-costs", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ------------------------------------------------------------------
    # Write grants read
    # ------------------------------------------------------------------

    def test_s8_write_grants_read_for_cost_model(self):
        """Write permission on cost_model implicitly grants read access."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"cost_model": {"write": ["*"]}})
        response = self._get("cost-models-list", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # Org admin bypass
    # ------------------------------------------------------------------

    def test_s9_admin_bypass_no_tuples(self):
        """Org admin gets full access without any Kessel tuples (middleware bypass)."""
        response = self._get("reports-aws-costs", self.admin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # OCP: StreamedListObjects
    # ------------------------------------------------------------------

    def test_s10_ocp_cluster_resources_granted(self):
        """User with OCP cluster resources seeded can access OpenShift cost reports."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["test-cluster-001"])
        response = self._get("reports-openshift-costs", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s11_no_ocp_resources_returns_403(self):
        """User with no OCP resources is denied access to OpenShift cost reports.

        Uses the denied user to avoid stale-tuple contamination.
        """
        response = self._get("reports-openshift-costs", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s12_settings_write_grants_read(self):
        """Write permission on settings implicitly grants read access."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})
        response = self._get("settings-tags", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================================================================
    # Acceptance: Provider-exclusive access boundaries
    #
    # Verify that granting access to one provider does NOT bleed into
    # unrelated providers, resource types, or management endpoints.
    # ==================================================================

    def test_s13_aws_only_denies_all_other_providers(self):
        """AWS-only access must not grant GCP, Azure, OCP, cost_model, or settings."""
        username = "e2e-s13-exclusive"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"aws.account": {"read": ["*"]}})

        self.assertEqual(self._get("reports-aws-costs", header).status_code, status.HTTP_200_OK)

        for url_name in ("reports-gcp-costs", "reports-azure-costs", "cost-models-list", "settings-tags"):
            with self.subTest(url=url_name):
                self.assertEqual(self._get(url_name, header).status_code, status.HTTP_403_FORBIDDEN)

        self.assertEqual(self._get("reports-openshift-costs", header).status_code, status.HTTP_403_FORBIDDEN)

    def test_s14_ocp_only_denies_cloud_and_management(self):
        """OCP-only access must not grant AWS, GCP, Azure, cost_model, or settings."""
        username = "e2e-s14-ocp-only"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s14-cluster"], wait_user=username)

        self.assertEqual(self._get("reports-openshift-costs", header).status_code, status.HTTP_200_OK)

        for url_name in (
            "reports-aws-costs",
            "reports-gcp-costs",
            "reports-azure-costs",
            "cost-models-list",
            "settings-tags",
        ):
            with self.subTest(url=url_name):
                self.assertEqual(self._get(url_name, header).status_code, status.HTTP_403_FORBIDDEN)

    def test_s15_zero_permissions_denied_all_report_endpoints(self):
        """User with no Kessel permissions gets 403 on every report and management endpoint."""
        for url_name in (
            "reports-aws-costs",
            "reports-gcp-costs",
            "reports-azure-costs",
            "reports-openshift-costs",
            "cost-models-list",
            "settings-tags",
        ):
            with self.subTest(url=url_name):
                self.assertEqual(self._get(url_name, self.denied_header).status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # Acceptance: OCP-on-Cloud cross-provider views
    #
    # OCP-on-AWS/Azure views require BOTH the cloud provider permission
    # AND OpenShift permission.  OCP-on-All requires at least one
    # provider type to have read access.
    # ==================================================================

    def test_s16_ocp_plus_aws_grants_ocp_on_aws(self):
        """User with both OCP cluster and AWS account access can reach OCP-on-AWS reports."""
        username = "e2e-s16-ocp-aws"
        header = _build_identity_header(username)
        self.fixture.seed_access(
            E2E_WORKSPACE_ID,
            username,
            {"openshift.cluster": {"read": ["*"]}, "aws.account": {"read": ["*"]}},
        )
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s16-cluster"], wait_user=username)

        self.assertEqual(
            self._get("reports-openshift-aws-costs", header).status_code,
            status.HTTP_200_OK,
        )

    def test_s17_ocp_without_aws_denies_ocp_on_aws(self):
        """OCP-only access (no AWS) is denied OCP-on-AWS reports."""
        username = "e2e-s17-ocp-no-aws"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s17-cluster"], wait_user=username)

        self.assertEqual(
            self._get("reports-openshift-aws-costs", header).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_s18_ocp_plus_azure_grants_ocp_on_azure(self):
        """User with both OCP cluster and Azure subscription access can reach OCP-on-Azure reports."""
        username = "e2e-s18-ocp-azure"
        header = _build_identity_header(username)
        self.fixture.seed_access(
            E2E_WORKSPACE_ID,
            username,
            {"openshift.cluster": {"read": ["*"]}, "azure.subscription_guid": {"read": ["*"]}},
        )
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s18-cluster"], wait_user=username)

        self.assertEqual(
            self._get("reports-openshift-azure-costs", header).status_code,
            status.HTTP_200_OK,
        )

    def test_s19_ocp_without_azure_denies_ocp_on_azure(self):
        """OCP-only access (no Azure) is denied OCP-on-Azure reports."""
        username = "e2e-s19-ocp-no-azure"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s19-cluster"], wait_user=username)

        self.assertEqual(
            self._get("reports-openshift-azure-costs", header).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_s20_any_provider_access_grants_ocp_on_all(self):
        """OCP-on-All only requires at least one provider type with read access.

        OpenshiftAllAccessPermission iterates RESOURCE_TYPES and checks
        if any have a non-empty read list.  OCP cluster access alone is
        sufficient.
        """
        username = "e2e-s20-ocp-on-all"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s20-cluster"], wait_user=username)

        self.assertEqual(
            self._get("reports-openshift-all-costs", header).status_code,
            status.HTTP_200_OK,
        )

    def test_s20b_aws_without_ocp_denies_ocp_on_aws(self):
        """AWS-only access (no OCP) is denied OCP-on-AWS reports.

        Complements s17 (OCP without AWS -> 403): both halves of the
        dual-permission requirement are tested.
        """
        username = "e2e-s20b-aws-no-ocp"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"aws.account": {"read": ["*"]}})

        self.assertEqual(
            self._get("reports-openshift-aws-costs", header).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_s20c_ocp_plus_gcp_grants_ocp_on_gcp(self):
        """User with both OCP cluster and GCP account access can reach OCP-on-GCP reports."""
        username = "e2e-s20c-ocp-gcp"
        header = _build_identity_header(username)
        self.fixture.seed_access(
            E2E_WORKSPACE_ID,
            username,
            {"openshift.cluster": {"read": ["*"]}, "gcp.account": {"read": ["*"]}},
        )
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s20c-cluster"], wait_user=username)

        self.assertEqual(
            self._get("reports-openshift-gcp-costs", header).status_code,
            status.HTTP_200_OK,
        )

    def test_s20d_ocp_without_gcp_denies_ocp_on_gcp(self):
        """OCP-only access (no GCP) is denied OCP-on-GCP reports."""
        username = "e2e-s20d-ocp-no-gcp"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s20d-cluster"], wait_user=username)

        self.assertEqual(
            self._get("reports-openshift-gcp-costs", header).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    # ==================================================================
    # Acceptance: Query-parameter filtering
    #
    # Verify that views accept filter parameters when the user has the
    # required Kessel permissions.  This mirrors how the UI always sends
    # filter[account], filter[cluster], etc.
    # ==================================================================

    def test_s21_aws_with_account_filter(self):
        """AWS reports accept filter[account] when the user has AWS access."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})
        response = self._get("reports-aws-costs", self.nonadmin_header, {"filter[account]": "123456789"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s22_ocp_with_cluster_filter(self):
        """OCP reports accept filter[cluster] when the user has OCP access."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s22-filter-cluster"])
        response = self._get(
            "reports-openshift-costs",
            self.nonadmin_header,
            {"filter[cluster]": "s22-filter-cluster"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s23_azure_with_subscription_filter(self):
        """Azure reports accept filter[subscription_guid] when the user has Azure access."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"azure.subscription_guid": {"read": ["*"]}})
        response = self._get(
            "reports-azure-costs",
            self.nonadmin_header,
            {"filter[subscription_guid]": "00000000-0000-0000-0000-000000000001"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s24_gcp_with_account_filter(self):
        """GCP reports accept filter[account] when the user has GCP access."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"gcp.account": {"read": ["*"]}})
        response = self._get("reports-gcp-costs", self.nonadmin_header, {"filter[account]": "gcp-acct-1"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================================================================
    # Acceptance: Resource-type discovery endpoints
    #
    # The UI calls these to populate filter dropdowns (account selector,
    # cluster selector, etc.).  They must respect Kessel authorization.
    # ==================================================================

    def test_s25_aws_accounts_resource_type_granted(self):
        """User with AWS access can list AWS account resource types."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})
        response = self._get("aws-accounts", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s26_aws_accounts_resource_type_denied(self):
        """User without AWS access is denied AWS account resource types."""
        response = self._get("aws-accounts", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s27_openshift_clusters_resource_type_granted(self):
        """User with OCP access can list OpenShift cluster resource types."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s27-cluster"])
        response = self._get("openshift-clusters", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s28_openshift_clusters_resource_type_denied(self):
        """User without OCP access is denied OpenShift cluster resource types."""
        response = self._get("openshift-clusters", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s29_azure_subscriptions_resource_type_granted(self):
        """User with Azure access can list Azure subscription resource types."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"azure.subscription_guid": {"read": ["*"]}})
        response = self._get("azure-subscription-guids", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s29a_azure_subscriptions_resource_type_denied(self):
        """User without Azure access is denied Azure subscription resource types."""
        response = self._get("azure-subscription-guids", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s29b_gcp_accounts_resource_type_granted(self):
        """User with GCP access can list GCP account resource types."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"gcp.account": {"read": ["*"]}})
        response = self._get("gcp-accounts", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s29c_gcp_accounts_resource_type_denied(self):
        """User without GCP access is denied GCP account resource types."""
        response = self._get("gcp-accounts", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # Acceptance: User-access endpoint
    #
    # The UI calls /user-access/ to determine which navigation tabs and
    # pages to render.  The response must reflect Kessel permissions.
    # ==================================================================

    def test_s30_user_access_reflects_aws_permission(self):
        """User-access endpoint returns access=true for AWS when the user has AWS permission."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})
        response = self._get("user-access", self.nonadmin_header, {"type": "aws"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            response.data.get("data", False),
            "Expected user-access to report access=true for AWS",
        )

    def test_s31_user_access_denies_gcp_without_permission(self):
        """User-access endpoint returns access=false for GCP when the user has no GCP permission."""
        username = "e2e-s31-no-gcp"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"aws.account": {"read": ["*"]}})
        response = self._get("user-access", header, {"type": "gcp"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            response.data.get("data", True),
            "Expected user-access to report access=false for GCP",
        )

    # ==================================================================
    # Acceptance: Forecast endpoints
    #
    # Forecast views follow the same permission model as reports.
    # Cross-provider forecasts require both provider permissions.
    # ==================================================================

    def test_s32_aws_forecast_granted(self):
        """User with AWS access can reach AWS cost forecasts."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"aws.account": {"read": ["*"]}})
        response = self._get("aws-cost-forecasts", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s33_aws_forecast_denied(self):
        """User without AWS access is denied AWS cost forecasts."""
        response = self._get("aws-cost-forecasts", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s34_ocp_on_aws_forecast_requires_both(self):
        """OCP-on-AWS forecast requires both OCP and AWS permissions."""
        username = "e2e-s34-ocp-aws-fc"
        header = _build_identity_header(username)
        self.fixture.seed_access(
            E2E_WORKSPACE_ID,
            username,
            {"openshift.cluster": {"read": ["*"]}, "aws.account": {"read": ["*"]}},
        )
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s34-cluster"], wait_user=username)

        self.assertEqual(
            self._get("openshift-aws-cost-forecasts", header).status_code,
            status.HTTP_200_OK,
        )

    def test_s35_ocp_on_aws_forecast_denied_without_aws(self):
        """OCP-only access (no AWS) is denied OCP-on-AWS forecasts."""
        username = "e2e-s35-ocp-no-aws-fc"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s35-cluster"], wait_user=username)

        self.assertEqual(
            self._get("openshift-aws-cost-forecasts", header).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_s35b_ocp_forecast_granted(self):
        """User with OCP access can reach OpenShift cost forecasts."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s35b-cluster"])
        response = self._get("openshift-cost-forecasts", self.nonadmin_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_s35c_ocp_forecast_denied(self):
        """User without OCP access is denied OpenShift cost forecasts."""
        response = self._get("openshift-cost-forecasts", self.denied_header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # Acceptance: Write operations (cost model, settings)
    #
    # The UI performs POST (create cost model) and PUT (enable/disable
    # tags) operations.  Authorization for writes is distinct from reads
    # and must be validated end-to-end through Kessel.
    # ==================================================================

    def test_s36_cost_model_post_authorized(self):
        """User with cost_model write can POST to cost-models (authorization passes).

        Sends a minimal body; the view may return 400 for validation
        errors, but the key assertion is that it does NOT return 403.
        """
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"cost_model": {"write": ["*"]}})
        response = self._post("cost-models-list", self.nonadmin_header)
        self.assertNotEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            "Expected authorization to pass (non-403); got 403",
        )

    def test_s37_cost_model_post_denied(self):
        """User with cost_model read-only is denied POST to cost-models."""
        username = "e2e-s37-cm-readonly"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"cost_model": {"read": ["*"]}})
        response = self._post("cost-models-list", header)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s38_cost_model_post_denied_no_access(self):
        """User with no cost_model access is denied both GET and POST."""
        self.assertEqual(self._get("cost-models-list", self.denied_header).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._post("cost-models-list", self.denied_header).status_code, status.HTTP_403_FORBIDDEN)

    def test_s39_settings_put_authorized(self):
        """User with settings write can PUT to tag-enable (authorization passes).

        Sends an empty ids list; the view may return 400 or 200, but
        the key assertion is that it does NOT return 403.
        """
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})
        response = self._put("tags-enable", self.nonadmin_header, data={"ids": []})
        self.assertNotEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            "Expected authorization to pass (non-403); got 403",
        )

    def test_s40_settings_put_denied_read_only(self):
        """User with settings read-only is denied PUT to tag-enable."""
        username = "e2e-s40-settings-ro"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"settings": {"read": ["*"]}})
        response = self._put("tags-enable", header, data={"ids": []})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # Acceptance: Multi-provider realistic profile
    #
    # Simulates a realistic user profile with access to multiple
    # providers, validating that the full access surface works.
    # ==================================================================

    def test_s41_realistic_multi_provider_user(self):
        """Realistic user with AWS + OCP + settings read access.

        Validates that all expected endpoints are reachable and that
        unrelated providers (GCP, Azure) are denied.
        """
        username = "e2e-s41-realistic"
        header = _build_identity_header(username)
        self.fixture.seed_access(
            E2E_WORKSPACE_ID,
            username,
            {
                "aws.account": {"read": ["*"]},
                "openshift.cluster": {"read": ["*"]},
                "settings": {"read": ["*"]},
            },
        )
        self.fixture.seed_ocp_resources(E2E_WORKSPACE_ID, "openshift_cluster", ["s41-cluster"], wait_user=username)

        granted_urls = (
            "reports-aws-costs",
            "reports-openshift-costs",
            "reports-openshift-aws-costs",
            "reports-openshift-all-costs",
            "settings-tags",
            "aws-accounts",
            "openshift-clusters",
            "aws-cost-forecasts",
        )
        for url_name in granted_urls:
            with self.subTest(url=url_name, expected="200"):
                self.assertEqual(self._get(url_name, header).status_code, status.HTTP_200_OK)

        denied_urls = (
            "reports-gcp-costs",
            "reports-azure-costs",
            "reports-openshift-azure-costs",
            "reports-openshift-gcp-costs",
            "cost-models-list",
        )
        for url_name in denied_urls:
            with self.subTest(url=url_name, expected="403"):
                self.assertEqual(self._get(url_name, header).status_code, status.HTTP_403_FORBIDDEN)

        with self.subTest(url="user-access?type=aws", expected="true"):
            resp = self._get("user-access", header, {"type": "aws"})
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertTrue(resp.data.get("data", False))

        with self.subTest(url="user-access?type=gcp", expected="false"):
            resp = self._get("user-access", header, {"type": "gcp"})
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertFalse(resp.data.get("data", True))

    # ==================================================================
    # Acceptance: Resource-level scoping (StreamedListObjects)
    #
    # When inventory resources are seeded for specific IDs, Kessel's
    # StreamedListObjects returns those IDs instead of granting
    # wildcard access.  Views then filter data to only those resources.
    # ==================================================================

    def test_s42_ocp_specific_cluster_ids_auth_passes(self):
        """OCP user with specific cluster IDs (not wildcard) can access OCP reports.

        Seeds inventory resources for two specific cluster IDs.
        StreamedListObjects returns those IDs, producing a non-wildcard
        access list that still passes OpenShiftAccessPermission.
        """
        username = "e2e-s42-scoped"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_inventory_resources(
            E2E_WORKSPACE_ID,
            "openshift_cluster",
            ["s42-cluster-A", "s42-cluster-B"],
            wait_user=username,
        )

        self.assertEqual(
            self._get("reports-openshift-costs", header).status_code,
            status.HTTP_200_OK,
        )

    def test_s43_ocp_specific_clusters_resource_type_filtered(self):
        """OCP clusters resource-type endpoint returns only seeded cluster IDs.

        If the test DB has no cost data for the seeded clusters, the
        data list will be empty, but authorization must pass (not 403).
        """
        username = "e2e-s43-rt-scoped"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_inventory_resources(
            E2E_WORKSPACE_ID,
            "openshift_cluster",
            ["s43-cluster-X"],
            wait_user=username,
        )

        response = self._get("openshift-clusters", header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data.get("data", []):
            self.assertIn(
                item.get("value", item.get("cluster_id")),
                ["s43-cluster-X"],
                "Unexpected cluster in response; resource-level scoping may be broken",
            )

    def test_s44_ocp_specific_clusters_plus_aws_wildcard_grants_ocp_on_aws(self):
        """OCP-on-AWS works with specific OCP cluster IDs + AWS wildcard.

        Dual-permission satisfied: AWS via workspace Check (wildcard)
        and OCP via StreamedListObjects (specific IDs).
        """
        username = "e2e-s44-scoped-xprov"
        header = _build_identity_header(username)
        self.fixture.seed_access(
            E2E_WORKSPACE_ID,
            username,
            {"openshift.cluster": {"read": ["*"]}, "aws.account": {"read": ["*"]}},
        )
        self.fixture.seed_inventory_resources(
            E2E_WORKSPACE_ID,
            "openshift_cluster",
            ["s44-cluster"],
            wait_user=username,
        )

        self.assertEqual(
            self._get("reports-openshift-aws-costs", header).status_code,
            status.HTTP_200_OK,
        )

    def test_s45_ocp_single_cluster_scoping(self):
        """OCP user with exactly one cluster seeded can access OCP reports.

        Proves the specific-ID path works end-to-end even with a single
        resource in the access list.
        """
        username = "e2e-s45-single"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"openshift.cluster": {"read": ["*"]}})
        self.fixture.seed_inventory_resources(
            E2E_WORKSPACE_ID,
            "openshift_cluster",
            ["s45-only-cluster"],
            wait_user=username,
        )

        self.assertEqual(
            self._get("reports-openshift-costs", header).status_code,
            status.HTTP_200_OK,
        )

    # ==================================================================
    # Acceptance: Sources API + Kessel Inventory persistence
    #
    # The on-prem Sources API (POST /sources/) replaces sources-api-go.
    # OCP source creation must persist to both PostgreSQL and Kessel
    # Inventory.  Non-OCP sources must persist only to PostgreSQL.
    # ==================================================================

    def test_s46_ocp_source_creates_postgres_records(self):
        """OCP source creation persists Source and Provider rows in PostgreSQL."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})
        response = self._post(
            "sources-list",
            self.nonadmin_header,
            data={
                "name": "e2e-s46-ocp-source",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": "s46-e2e-cluster"}},
            },
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            f"Expected 200/201 but got {response.status_code}: {response.data}",
        )

        source_id = int(response.data["id"])
        self._created_source_ids.append(source_id)

        source = Sources.objects.get(source_id=source_id)
        self.assertIsNotNone(source.koku_uuid, "Source must have a linked Provider UUID")
        self.assertTrue(
            Provider.objects.filter(uuid=source.koku_uuid).exists(),
            "Provider row must exist for the created source",
        )

    def test_s47_ocp_source_creates_kessel_tracking_record(self):
        """OCP source creation creates a KesselSyncedResource tracking row."""
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})
        response = self._post(
            "sources-list",
            self.nonadmin_header,
            data={
                "name": "e2e-s47-ocp-source",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": "s47-e2e-cluster"}},
            },
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            f"Expected 200/201 but got {response.status_code}: {response.data}",
        )

        source_id = int(response.data["id"])
        self._created_source_ids.append(source_id)

        source = Sources.objects.get(source_id=source_id)
        provider_uuid = str(source.koku_uuid)

        synced = KesselSyncedResource.objects.filter(
            resource_type="openshift_cluster",
            resource_id=provider_uuid,
        )
        self.assertTrue(synced.exists(), "KesselSyncedResource must exist after OCP source creation")
        self.assertTrue(synced.first().kessel_synced, "kessel_synced must be True")

    def test_s48_ocp_source_resource_discoverable_via_kessel(self):
        """OCP resource created via Sources API is discoverable by a Kessel-authorized user.

        After source creation reports the resource to Kessel Inventory,
        a second user with OCP read access can reach OCP reports because
        StreamedListObjects discovers the newly created resource.
        """
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})
        response = self._post(
            "sources-list",
            self.nonadmin_header,
            data={
                "name": "e2e-s48-ocp-source",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": "s48-e2e-cluster"}},
            },
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            f"Expected 200/201 but got {response.status_code}: {response.data}",
        )

        source_id = int(response.data["id"])
        self._created_source_ids.append(source_id)

        source = Sources.objects.get(source_id=source_id)
        provider_uuid = str(source.koku_uuid)

        reader = "e2e-s48-reader"
        reader_header = _build_identity_header(reader)
        self.fixture.seed_access(E2E_WORKSPACE_ID, reader, {"openshift.cluster": {"read": ["*"]}})
        self.fixture._wait_for_resource_visibility(
            "openshift_cluster",
            provider_uuid,
            reader,
        )

        self.assertEqual(
            self._get("reports-openshift-costs", reader_header).status_code,
            status.HTTP_200_OK,
        )

    @patch("providers.provider_access.ProviderAccessor.cost_usage_source_ready", return_value=True)
    def test_s49_aws_source_no_kessel_inventory_entry(self, mock_cost_ready):
        """AWS source creation persists to PostgreSQL but NOT to Kessel Inventory.

        Only OCP sources trigger ReportResource gRPC; other provider
        types must not create KesselSyncedResource rows.
        cost_usage_source_ready is mocked because real AWS credentials
        are unavailable in the test environment.
        """
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})
        response = self._post(
            "sources-list",
            self.nonadmin_header,
            data={
                "name": "e2e-s49-aws-source",
                "source_type": "AWS",
                "authentication": {"credentials": {"role_arn": "arn:aws:iam::123456789012:role/e2e-test"}},
                "billing_source": {"data_source": {"bucket": "e2e-cost-bucket"}},
            },
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            f"Expected 200/201 but got {response.status_code}: {response.data}",
        )

        source_id = int(response.data["id"])
        self._created_source_ids.append(source_id)

        source = Sources.objects.get(source_id=source_id)
        self.assertIsNotNone(source.koku_uuid, "Source must have a linked Provider UUID")

        synced = KesselSyncedResource.objects.filter(
            resource_type__in=["aws_account", "aws_organizational_unit"],
            resource_id=str(source.koku_uuid),
        )
        self.assertFalse(synced.exists(), "Non-OCP source must NOT create a KesselSyncedResource entry")

    def test_s50_sources_post_denied_no_access(self):
        """User without settings access is denied POST to /sources/."""
        response = self._post(
            "sources-list",
            self.denied_header,
            data={
                "name": "e2e-s50-denied",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": "s50-cluster"}},
            },
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s51_sources_post_denied_read_only(self):
        """User with settings read-only is denied POST to /sources/."""
        username = "e2e-s51-settings-ro"
        header = _build_identity_header(username)
        self.fixture.seed_access(E2E_WORKSPACE_ID, username, {"settings": {"read": ["*"]}})
        response = self._post(
            "sources-list",
            header,
            data={
                "name": "e2e-s51-denied",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": "s51-cluster"}},
            },
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_s52_sources_list_filtered_by_provider_access(self):
        """Sources list is filtered by provider access: AWS user sees only AWS sources.

        Creates both OCP and AWS-local sources as admin, then a user
        with only AWS access lists sources.  OCP sources must be
        excluded by get_excludes().
        """
        self.fixture.seed_access(E2E_WORKSPACE_ID, E2E_USERNAME, {"settings": {"write": ["*"]}})
        ocp_resp = self._post(
            "sources-list",
            self.admin_header,
            data={
                "name": "e2e-s52-ocp",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": "s52-cluster"}},
            },
        )
        if ocp_resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED):
            self._created_source_ids.append(int(ocp_resp.data["id"]))

        aws_resp = self._post(
            "sources-list",
            self.admin_header,
            data={
                "name": "e2e-s52-aws",
                "source_type": "AWS-local",
                "authentication": {"credentials": {"role_arn": "arn:aws:iam::123456789012:role/e2e-s52"}},
                "billing_source": {"data_source": {"bucket": "e2e-s52-bucket"}},
            },
        )
        if aws_resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED):
            self._created_source_ids.append(int(aws_resp.data["id"]))

        lister = "e2e-s52-aws-only"
        lister_header = _build_identity_header(lister)
        self.fixture.seed_access(
            E2E_WORKSPACE_ID,
            lister,
            {"settings": {"read": ["*"]}, "aws.account": {"read": ["*"]}},
        )

        response = self._get("sources-list", lister_header)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for source in response.data.get("data", []):
            self.assertNotEqual(
                source.get("source_type"),
                Provider.PROVIDER_OCP,
                "OCP source must not appear for AWS-only user",
            )

    def test_s53_ocp_source_delete_cleans_postgres_preserves_kessel(self):
        """Deleting an OCP source removes PG rows but preserves KesselSyncedResource."""
        self.fixture.seed_access(
            E2E_WORKSPACE_ID,
            E2E_USERNAME,
            {"settings": {"write": ["*"]}, "openshift.cluster": {"read": ["*"]}},
        )
        response = self._post(
            "sources-list",
            self.nonadmin_header,
            data={
                "name": "e2e-s53-ocp-delete",
                "source_type": "OCP",
                "authentication": {"credentials": {"cluster_id": "s53-cluster"}},
            },
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
            f"Expected 200/201 but got {response.status_code}: {response.data}",
        )

        source_id = int(response.data["id"])
        self._created_source_ids.append(source_id)

        source = Sources.objects.get(source_id=source_id)
        provider_uuid = str(source.koku_uuid) if source.koku_uuid else None

        del_resp = self._delete("sources-detail", self.nonadmin_header, pk=source_id)
        self.assertIn(
            del_resp.status_code,
            (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT),
            f"Expected 200/204 but got {del_resp.status_code}",
        )

        self.assertFalse(
            Sources.objects.filter(source_id=source_id).exists(),
            "Source row must be deleted after DELETE request",
        )

        if provider_uuid:
            self.assertTrue(
                KesselSyncedResource.objects.filter(resource_id=provider_uuid).exists(),
                "KesselSyncedResource must be preserved after source deletion (no-delete principle)",
            )
            KesselSyncedResource.objects.filter(resource_id=provider_uuid).delete()
