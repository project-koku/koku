#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Sources Access Permissions."""
from unittest.mock import Mock

from django.test import TestCase

from api.common.permissions.sources_access import SourcesAccessPermission
from api.iam.models import User


class SourcesAccessPermissionTest(TestCase):
    """Test the sources access permission."""

    def test_has_perm_admin(self):
        """Test that an admin user can execute."""
        user = Mock(spec=User, admin=True)
        req = Mock(user=user)
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_no_access(self):
        """Test that a user with no access is denied."""
        user = Mock(spec=User, admin=False, access=None)
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_empty_access(self):
        """Test that a user with empty access is denied."""
        user = Mock(spec=User, admin=False, access={})
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_read_access_on_get(self):
        """Test that a user with sources read access can GET."""
        access = {"sources": {"read": ["*"]}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_read_access_on_head(self):
        """Test that a user with sources read access can HEAD."""
        access = {"sources": {"read": ["*"]}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="HEAD")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_no_read_on_get(self):
        """Test that a user without sources read access is denied on GET."""
        access = {"sources": {"read": []}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_write_access_on_post(self):
        """Test that a user with sources write access can POST."""
        access = {"sources": {"write": ["*"], "read": ["*"]}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="POST")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_write_access_on_patch(self):
        """Test that a user with sources write access can PATCH."""
        access = {"sources": {"write": ["*"], "read": ["*"]}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="PATCH")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_write_access_on_delete(self):
        """Test that a user with sources write access can DELETE."""
        access = {"sources": {"write": ["*"], "read": ["*"]}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="DELETE")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_no_write_on_post(self):
        """Test that a user without sources write access is denied on POST."""
        access = {"sources": {"read": ["*"], "write": []}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="POST")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_read_only_on_post(self):
        """Test that a read-only user is denied on POST."""
        access = {"sources": {"read": ["*"]}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="POST")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_other_access_only(self):
        """Test that a user with only non-sources access is denied."""
        access = {"cost_model": {"read": ["*"], "write": ["*"]}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_non_wildcard_read_denied(self):
        """Test that non-wildcard read access is denied (sources is global, not per-resource)."""
        access = {"sources": {"read": ["some-source-id"]}}
        user = Mock(spec=User, admin=False, access=access)
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        result = perm.has_permission(request=req, view=None)
        self.assertFalse(result)
