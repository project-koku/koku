#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Ingress Access Permissions."""
from unittest.mock import Mock
from unittest.mock import patch

from django.test import override_settings
from django.test import TestCase

from api.common.permissions import RESOURCE_TYPES
from api.common.permissions.ingress_access import IngressAccessPermission
from api.iam.models import User


class IngressAccessPermissionTest(TestCase):
    """Test the Ingress Access Permissions."""

    def setUp(self):
        """Set up test fixtures."""
        self.permission = IngressAccessPermission()

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_success(self, _):
        """Test that a user with read access can execute GET requests."""
        user = Mock(spec=User, access={"aws.account": {"read": ["*"]}}, admin=False, customer=None)
        req = Mock(user=user, method="GET")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_all_resource_types(self, _):
        """Test read access with all valid resource types."""
        for resource_type in RESOURCE_TYPES:
            with self.subTest(resource_type=resource_type):
                access = {resource_type: {"read": ["*"]}}
                user = Mock(spec=User, access=access, admin=False, customer=None)
                req = Mock(user=user, method="GET")
                self.assertTrue(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_failure_no_access(self, _):
        """Test that a user with no access dict cannot execute GET requests."""
        user = Mock(spec=User, access=None, admin=False, customer=None)
        req = Mock(user=user, method="GET")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_failure_wrong_resource(self, _):
        """Test that a user with access to other resources cannot access ingress."""
        user = Mock(spec=User, access={"other.resource": {"read": ["*"]}}, admin=False, customer=None)
        req = Mock(user=user, method="GET")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_has_read_access_failure_empty_read_list(self, _):
        """Test that a user with empty read list cannot access."""
        user = Mock(spec=User, access={"aws.account": {"read": []}}, admin=False, customer=None)
        req = Mock(user=user, method="GET")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    @override_settings(ENHANCED_ORG_ADMIN=True)
    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_admin_bypass_read(self, _):
        """Test that an org admin can access GET requests."""
        user = Mock(spec=User, access={}, admin=True, customer=None)
        req = Mock(user=user, method="GET")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @override_settings(ENHANCED_ORG_ADMIN=True)
    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_admin_bypass_write(self, _):
        """Test that an org admin can access POST requests."""
        user = Mock(spec=User, access={}, admin=True, customer=None)
        req = Mock(user=user, method="POST")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @override_settings(ENHANCED_ORG_ADMIN=False)
    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_admin_no_bypass_when_enhanced_org_admin_disabled(self, _):
        """Test that admin flag is ignored when ENHANCED_ORG_ADMIN is False."""
        user = Mock(spec=User, access={}, admin=True, customer=None)
        req = Mock(user=user, method="POST")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_write_access_denied_for_non_admin(self, _):
        """Test that non-admin users cannot POST even with read access."""
        user = Mock(spec=User, access={"aws.account": {"read": ["*"]}}, admin=False, customer=None)
        req = Mock(user=user, method="POST")
        self.assertFalse(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=True)
    def test_grace_period_allows_read_access(self, _):
        """Test that grace period allows read access."""
        customer = Mock(schema_name="test_schema")
        user = Mock(spec=User, access={}, admin=False, customer=customer)
        req = Mock(user=user, method="GET")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=True)
    def test_grace_period_allows_write_access(self, _):
        """Test that grace period allows write access."""
        customer = Mock(schema_name="test_schema")
        user = Mock(spec=User, access={}, admin=False, customer=customer)
        req = Mock(user=user, method="POST")
        self.assertTrue(self.permission.has_permission(request=req, view=None))

    @patch("api.common.permissions.ingress_access.is_ingress_rbac_grace_period_enabled", return_value=False)
    def test_no_customer_no_grace_period(self, mock_grace):
        """Test that grace period check is skipped when no customer."""
        user = Mock(spec=User, access={"aws.account": {"read": ["*"]}}, admin=False, customer=None)
        req = Mock(user=user, method="GET")
        self.assertTrue(self.permission.has_permission(request=req, view=None))
        # Grace period should not be called when customer is None
        mock_grace.assert_not_called()
