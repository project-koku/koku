#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Resource Type Access Permissions."""
from unittest.mock import Mock

from django.test import TestCase

from api.common.permissions.resource_type_access import ResourceTypeAccessPermission
from api.iam.models import User


class ResourceTypeAccessPermissionTest(TestCase):
    """Test the resource type access permission."""

    def test_has_perm_admin(self):
        """Test that an admin user can execute."""
        user = Mock(spec=User, admin=True)
        req = Mock(user=user)
        accessPerm = ResourceTypeAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_with_no_access_on_get(self):
        """Test that a user read."""
        user = Mock(spec=User, admin=False)
        req = Mock(user=user, method="GET")
        accessPerm = ResourceTypeAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_with_no_access_on_post(self):
        """Test that a user cannot execute POST."""
        user = Mock(spec=User, admin=False)
        req = Mock(user=user, method="POST", META={"PATH_INFO": "http://localhost/api/v1/resource-types/"})
        accessPerm = ResourceTypeAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)
