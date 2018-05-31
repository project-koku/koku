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
"""Test the project middleware."""
import random
import string
from unittest.mock import Mock, patch

from django.test import TestCase

from api.iam.models import Tenant
from koku.middleware import KokuTenantMiddleware


class KokuTenantMiddlewareTest(TestCase):
    """Tests against the koku tenant middleware."""

    def setUp(self):
        """Set up middleware tests."""
        self.schema_name = 'test_schema'
        Tenant.objects.get_or_create(schema_name=self.schema_name)

    @patch('koku.middleware.Customer')
    def test_get_tenant_with_user(self, mock_model):
        """Test that the customer tenant is returned."""
        mock_request = Mock()
        mock_group = Mock()
        mock_customer = Mock()
        mock_group.id = ''.join([random.choice(string.digits)
                                 for _ in range(6)])
        mock_user_groups = mock_request.user.return_value.groups.return_value
        mock_user_groups.first.return_value = mock_group
        mock_customer.schema_name = self.schema_name
        mock_model.objects.get.return_value = mock_customer

        middleware = KokuTenantMiddleware()
        result = middleware.get_tenant(Tenant, 'localhost', mock_request)

        self.assertEqual(result.schema_name, self.schema_name)

    def test_get_default_tenant(self):
        """Test that the public tenant is returned."""
        mock_request = Mock()
        del mock_request.user
        middleware = KokuTenantMiddleware()
        result = middleware.get_tenant(Tenant, 'localhost', mock_request)

        self.assertEqual(result.schema_name, 'public')
