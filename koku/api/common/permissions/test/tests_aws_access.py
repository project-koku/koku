#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Tests for AWS Access Permissions."""

from unittest.mock import Mock

from django.test import TestCase

from api.common.permissions.aws_access import AwsAccessPermission
from api.iam.models import User


class AwsAccessPermissionTest(TestCase):
    """Test the AWS access permission."""

    def test_has_perm_admin(self):
        """Test that an admin user can execute."""
        user = Mock(spec=User, admin=True)
        req = Mock(user=user)
        accessPerm = AwsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_none_access(self):
        """Test that a user with no access cannot execute."""
        user = Mock(spec=User, access=None, admin=False)
        req = Mock(user=user)
        accessPerm = AwsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_with_access_on_get(self):
        """Test that a user with access can execute."""
        access = {'aws.account': {'read': ['*']}}
        user = Mock(spec=User, access=access, admin=False)
        req = Mock(user=user, method='GET')
        accessPerm = AwsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertTrue(result)

    def test_has_perm_with_access_on_put(self):
        """Test that a user with access can execute."""
        access = {'aws.account': {'read': ['*']}}
        user = Mock(spec=User, access=access, admin=False)
        req = Mock(user=user, method='PUT')
        accessPerm = AwsAccessPermission()
        result = accessPerm.has_permission(request=req, view=None)
        self.assertFalse(result)
