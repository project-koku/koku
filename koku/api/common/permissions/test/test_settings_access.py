#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Settings Access Permissions."""
from unittest.mock import Mock

from django.test import override_settings
from django.test import TestCase

from api.common.permissions.settings_access import SettingsAccessPermission
from api.iam.models import User


class SettingsAccessPermissionTest(TestCase):
    """Test the settings access permission."""

    @override_settings(ENHANCED_ORG_ADMIN=True)
    def test_has_perm_admin(self):
        """Test that an admin user can execute."""
        user = Mock(spec=User, admin=True, access={"settings": {"read": ["*"], "write": ["*"]}})
        req = Mock(user=user)
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_with_access_on_get(self):
        """Test that a user read."""
        user = Mock(spec=User, admin=False, access={})
        req = Mock(user=user, method="GET")
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_with_no_access_on_post(self):
        """Test that a user cannot execute POST."""
        user = Mock(spec=User, admin=False, access={})
        req = Mock(user=user, method="POST", META={"PATH_INFO": "http://localhost/api/v1/settings/"})
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_get_with_settings_read_returns_true(self):
        user = Mock(spec=User, admin=False, access={"settings": {"read": ["*"]}})
        req = Mock(user=user, method="GET")
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_get_with_empty_settings_read_returns_false(self):
        user = Mock(spec=User, admin=False, access={"settings": {"read": []}, "openshift.cluster": {"read": ["*"]}})
        req = Mock(user=user, method="GET")
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_post_with_settings_write_wildcard_returns_true(self):
        user = Mock(spec=User, admin=False, access={"settings": {"write": ["*"]}})
        req = Mock(user=user, method="POST")
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_post_with_settings_write_no_wildcard_returns_false(self):
        user = Mock(spec=User, admin=False, access={"settings": {"write": ["specific-id"]}})
        req = Mock(user=user, method="POST")
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_access_none_returns_false(self):
        user = Mock(spec=User, admin=False, access=None)
        req = Mock(user=user, method="DELETE")
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    @override_settings(ENHANCED_ORG_ADMIN=False)
    def test_admin_not_bypassed_when_enhanced_org_admin_false(self):
        user = Mock(spec=User, admin=True, access={})
        req = Mock(user=user, method="POST")
        accessPerm = SettingsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)
