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

from api.common.permissions.object_owner import IsObjectOwner
from api.iam.models import User, UserPreference
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase


class IsObjectOwnerTest(IamTestCase):
    """Test the is object owner permission."""

    def setUp(self):
        """Set up the user view tests."""
        super().setUp()
        self.user_data = self._create_user_data()
        self.customer = self._create_customer_data()
        self.request_context = self._create_request_context(self.customer,
                                                            self.user_data)
        self.headers = self.request_context['request'].META
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
        self.user = User.objects.get(username=self.user_data['username'])

    def test_has_permission_no_user(self):
        """Test that empty user cannot execute."""
        req = Mock(user=None)
        o_perm = IsObjectOwner()
        pref = Mock(spec=UserPreference)
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertFalse(result)

    def test_has_perm_auth_user_get_unowned(self):
        """Test that an authenticated user can not read unowned objects."""
        user_data = self._create_user_data()
        request_context = self._create_request_context(self.customer, user_data, False)
        serializer = UserSerializer(data=user_data, context=request_context)
        if serializer.is_valid(raise_exception=True):
            new_user = serializer.save()

        req = Mock(user=new_user.username)
        pref = Mock(spec=UserPreference)
        o_perm = IsObjectOwner()
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertFalse(result)

    def test_has_perm_auth_user_get_owned(self):
        """Test that an authenticated user can read owned objects."""
        req = Mock(user=self.user.username)
        pref = Mock(spec=UserPreference, user=User(id=self.user.id, uuid=self.user.uuid))
        o_perm = IsObjectOwner()
        result = o_perm.has_object_permission(request=req, view=None, obj=pref)
        self.assertTrue(result)
