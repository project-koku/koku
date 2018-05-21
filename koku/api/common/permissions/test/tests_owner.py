#
# Copyright 2018 Red Hat, Inc.
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
"""Tests for Permissions."""

from unittest.mock import Mock
from uuid import uuid4

from django.test import TestCase

from api.common.permissions.owner import IsOwner
from api.iam.models import User, UserPreference


class IsOwnerTest(TestCase):
    """Test the user view."""

    def test_has_permission_no_user(self):
        """Test that empty user cannot execute."""
        req = Mock(user=None)
        o_perm = IsOwner()
        pref = Mock(spec=UserPreference)
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertFalse(result)

    def test_has_perm_no_auth_user(self):
        """Test that unauthenticated user cannot execute."""
        user = Mock(spec=User, is_authenticated=False)
        req = Mock(user=user)
        pref = Mock(spec=UserPreference)
        o_perm = IsOwner()
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertFalse(result)

    def test_has_perm_auth_user_get_unowned(self):
        """Test that an authenticated user can not read unowned objects."""
        user = Mock(spec=User, is_authenticated=True)
        req = Mock(user=user, method='GET')
        pref = Mock(spec=UserPreference)
        o_perm = IsOwner()
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertFalse(result)

    def test_has_perm_auth_user_get_owned(self):
        """Test that an authenticated user can read owned objects."""
        user = Mock(spec=User, is_authenticated=True, uuid=uuid4())
        req = Mock(user=user, method='GET')
        pref = Mock(spec=UserPreference, user=User(id=user.id, uuid=user.uuid))
        o_perm = IsOwner()
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertTrue(result)

    def test_has_perm_auth_user_post_unowned(self):
        """Test that an non-owner user cannot execute a POST."""
        user = Mock(spec=User, is_authenticated=True)
        req = Mock(user=user, method='POST')
        pref = Mock(spec=UserPreference)
        o_perm = IsOwner()
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertFalse(result)

    def test_has_perm_auth_user_post_owned(self):
        """Test that an owner user can execute a POST."""
        user = Mock(spec=User, is_authenticated=True, uuid=uuid4())
        req = Mock(user=user, method='POST')
        pref = Mock(spec=UserPreference, user=User(id=user.id, uuid=user.uuid))
        o_perm = IsOwner()
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertTrue(result)
