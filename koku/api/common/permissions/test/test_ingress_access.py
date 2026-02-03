#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Ingress Access Permissions."""
from unittest.mock import Mock
from unittest.mock import patch

from django.test import override_settings
from django.test import TestCase

from api.common.permissions.ingress_access import IngressAccessPermission
from api.iam.models import User


class IngressAccessPermissionTest(TestCase):
    """Test the Ingress Access Permissions."""

    def setUp(self):
        """Set up test fixtures."""
        self.permission = IngressAccessPermission()
        self.customer = Mock(schema_name="test_schema")

    # No customer tests

    def test_no_customer_returns_false(self):
        """Test that permission is denied when user has no customer attribute."""
        user = Mock(spec=User, access={"settings": {"read": ["*"]}}, admin=False, customer=None)
        req = Mock(user=user, method="GET")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    def test_no_customer_admin_returns_false(self):
        """Test that even admins are denied when no customer attribute."""
        user = Mock(spec=User, access={}, admin=True, customer=None)
        req = Mock(user=user, method="GET")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    # Grace period tests

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=True)
    def test_grace_period_allows_read_access(self, _):
        """Test that grace period allows read access regardless of RBAC."""
        user = Mock(spec=User, access={}, admin=False, customer=self.customer)
        req = Mock(user=user, method="GET")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=True)
    def test_grace_period_allows_write_access(self, _):
        """Test that grace period allows write access regardless of RBAC."""
        user = Mock(spec=User, access={}, admin=False, customer=self.customer)
        req = Mock(user=user, method="POST")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=True)
    def test_grace_period_bypasses_rbac_check(self, mock_grace):
        """Test that grace period is checked with customer schema_name."""
        user = Mock(spec=User, access={}, admin=False, customer=self.customer)
        req = Mock(user=user, method="GET")
        self.assertTrue(self.permission.has_permission(request=req, view=None))
        mock_grace.assert_called_once_with("test_schema")

    # Read access tests (delegated to SettingsAccessPermission)

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_with_settings_read(self, _):
        """Test that a user with settings read access can execute GET requests."""
        user = Mock(spec=User, access={"settings": {"read": ["*"]}}, admin=False, customer=self.customer)
        req = Mock(user=user, method="GET")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_failure_no_access(self, _):
        """Test that a user with no access dict cannot execute GET requests."""
        user = Mock(spec=User, access=None, admin=False, customer=self.customer)
        req = Mock(user=user, method="GET")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_failure_wrong_resource(self, _):
        """Test that a user with access to other resources cannot access ingress."""
        user = Mock(spec=User, access={"other.resource": {"read": ["*"]}}, admin=False, customer=self.customer)
        req = Mock(user=user, method="GET")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_failure_empty_read_list(self, _):
        """Test that a user with empty read list cannot access."""
        user = Mock(spec=User, access={"settings": {"read": []}}, admin=False, customer=self.customer)
        req = Mock(user=user, method="GET")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    # Write access tests (delegated to SettingsAccessPermission)

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_write_access_with_settings_write_wildcard(self, _):
        """Test that a user with settings write wildcard can POST."""
        user = Mock(spec=User, access={"settings": {"write": ["*"]}}, admin=False, customer=self.customer)
        req = Mock(user=user, method="POST")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_write_access_denied_without_wildcard(self, _):
        """Test that write access requires wildcard in settings.write."""
        user = Mock(spec=User, access={"settings": {"write": ["some_value"]}}, admin=False, customer=self.customer)
        req = Mock(user=user, method="POST")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_write_access_denied_with_only_read(self, _):
        """Test that non-admin users cannot POST with only read access."""
        user = Mock(spec=User, access={"settings": {"read": ["*"]}}, admin=False, customer=self.customer)
        req = Mock(user=user, method="POST")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    # Admin bypass tests (delegated to SettingsAccessPermission)

    @override_settings(ENHANCED_ORG_ADMIN=True)
    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_admin_bypass_read(self, _):
        """Test that an org admin can access GET requests."""
        user = Mock(spec=User, access={}, admin=True, customer=self.customer)
        req = Mock(user=user, method="GET")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @override_settings(ENHANCED_ORG_ADMIN=True)
    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_admin_bypass_write(self, _):
        """Test that an org admin can access POST requests."""
        user = Mock(spec=User, access={}, admin=True, customer=self.customer)
        req = Mock(user=user, method="POST")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @override_settings(ENHANCED_ORG_ADMIN=False)
    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_admin_no_bypass_when_enhanced_org_admin_disabled(self, _):
        """Test that admin flag is ignored when ENHANCED_ORG_ADMIN is False."""
        user = Mock(spec=User, access={}, admin=True, customer=self.customer)
        req = Mock(user=user, method="POST")
        self.assertFalse(self.permission.has_permission(request=req, view=None))
