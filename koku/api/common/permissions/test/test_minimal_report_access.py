#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for Settings Access Permissions."""
from unittest.mock import Mock

from django.test import TestCase

from api.common.permissions.minimal_report_access import MinimalReportAccessPermission
from api.iam.models import User


class MinimalReportAccessPermissionTest(TestCase):
    """Test the settings access permission."""

    def test_has_perm_admin(self):
        """Test that an admin user can execute."""
        user = Mock(spec=User, admin=True)
        req = Mock(user=user)
        accessPerm = MinimalReportAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_with_access_on_get(self):
        """Test that a user read."""
        user = Mock(spec=User, admin=False)
        req = Mock(user=user, method="GET")
        accessPerm = MinimalReportAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_with_no_access_on_post(self):
        """Test that a user cannot execute POST."""
        user = Mock(spec=User, admin=False)
        req = Mock(user=user, method="POST", META={"PATH_INFO": "http://localhost/api/v1/ingress/minimal-reports/"})
        accessPerm = MinimalReportAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)
