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
from unittest.mock import Mock, patch

from django.test import TestCase

from api.common.permissions.customer_owner import IsCustomerOwner
from api.iam.models import Customer


def get_fake_customer():
    """Mock a fake customer."""
    objects = Mock()
    objects.get.return_value = Customer()
    return objects


class IsCustomerOwnerTest(TestCase):
    """Test the customer view."""

    def test_has_permission_no_user(self):
        """Test that empty user cannot execute."""
        req = Mock()
        req.user = None
        co_perm = IsCustomerOwner()
        result = co_perm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_no_auth_user(self):
        """Test that unauthenticated user cannot execute."""
        req = Mock()
        user = Mock()
        user.is_authenticated = False
        req.user = user
        co_perm = IsCustomerOwner()
        result = co_perm.has_permission(request=req, view=None)
        self.assertFalse(result)

    def test_has_perm_auth_user_get(self):
        """Test that an authenticated user can execute a GET."""
        req = Mock()
        user = Mock()
        user.is_authenticated = True
        req.user = user
        req.method = 'GET'
        co_perm = IsCustomerOwner()
        result = co_perm.has_permission(request=req, view=None)
        self.assertTrue(result)

    @patch('api.common.permissions.customer_owner.Customer.objects.get',
           new_callable=get_fake_customer)
    def test_has_perm_auth_user_post(self, get_obj):
        """Test that an non-customer owner cannot execute a POST."""
        req = Mock()
        user = Mock()
        group = Mock()
        group.id = 1
        user.is_authenticated = True
        user.groups.first.return_value = group
        req.user = user
        req.method = 'POST'
        co_perm = IsCustomerOwner()
        result = co_perm.has_permission(request=req, view=None)
        self.assertFalse(result)
        get_obj.assert_called_once()
