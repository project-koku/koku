#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for SourcesAccessPermission."""
from unittest.mock import Mock

from django.test import override_settings
from django.test import TestCase

from api.common.permissions.sources_access import SourcesAccessPermission
from api.iam.models import User


class SourcesAccessPermissionTest(TestCase):
    """Test the sources access permission."""

    @override_settings(ENHANCED_ORG_ADMIN=True)
    def test_admin_bypass(self):
        user = Mock(spec=User, admin=True, access=None)
        req = Mock(user=user)
        perm = SourcesAccessPermission()
        self.assertTrue(perm.has_permission(request=req, view=None))

    @override_settings(ENHANCED_ORG_ADMIN=False)
    def test_admin_not_bypassed_when_enhanced_org_admin_false(self):
        user = Mock(spec=User, admin=True, access={})
        req = Mock(user=user, method="POST")
        perm = SourcesAccessPermission()
        self.assertFalse(perm.has_permission(request=req, view=None))

    def test_read_allowed_with_integration_access(self):
        user = Mock(
            spec=User,
            admin=False,
            access={"integration": {"read": ["source-uuid-1", "source-uuid-2"]}},
        )
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        self.assertTrue(perm.has_permission(request=req, view=None))

    def test_read_allowed_with_wildcard_integration_access(self):
        user = Mock(
            spec=User,
            admin=False,
            access={"integration": {"read": ["*"]}},
        )
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        self.assertTrue(perm.has_permission(request=req, view=None))

    def test_read_denied_with_no_integration_access(self):
        user = Mock(spec=User, admin=False, access={})
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        self.assertFalse(perm.has_permission(request=req, view=None))

    def test_read_denied_with_empty_integration_list(self):
        user = Mock(
            spec=User,
            admin=False,
            access={"integration": {"read": []}},
        )
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        self.assertFalse(perm.has_permission(request=req, view=None))

    def test_read_denied_with_none_access(self):
        user = Mock(spec=User, admin=False, access=None)
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        self.assertFalse(perm.has_permission(request=req, view=None))

    def test_read_denied_with_other_resource_access_only(self):
        """Integration access is required; other resource access alone is insufficient."""
        user = Mock(
            spec=User,
            admin=False,
            access={"openshift.cluster": {"read": ["*"]}},
        )
        req = Mock(user=user, method="GET")
        perm = SourcesAccessPermission()
        self.assertFalse(perm.has_permission(request=req, view=None))

    def test_write_requires_settings_write(self):
        user = Mock(
            spec=User,
            admin=False,
            access={"settings": {"write": ["*"]}, "integration": {"read": ["*"]}},
        )
        req = Mock(user=user, method="POST")
        perm = SourcesAccessPermission()
        self.assertTrue(perm.has_permission(request=req, view=None))

    def test_write_denied_without_settings_write(self):
        user = Mock(
            spec=User,
            admin=False,
            access={"integration": {"read": ["*"]}},
        )
        req = Mock(user=user, method="POST")
        perm = SourcesAccessPermission()
        self.assertFalse(perm.has_permission(request=req, view=None))

    def test_write_denied_with_settings_read_only(self):
        user = Mock(
            spec=User,
            admin=False,
            access={"settings": {"read": ["*"], "write": []}},
        )
        req = Mock(user=user, method="DELETE")
        perm = SourcesAccessPermission()
        self.assertFalse(perm.has_permission(request=req, view=None))
