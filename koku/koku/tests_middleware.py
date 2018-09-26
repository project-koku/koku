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
from unittest.mock import Mock

from api.iam.models import Customer, Tenant, User
from api.iam.serializers import (UserSerializer,
                                 create_schema_name)
from api.iam.test.iam_test_case import IamTestCase
from koku.middleware import (HttpResponseUnauthorizedRequest,
                             IdentityHeaderMiddleware,
                             KokuTenantMiddleware)


class KokuTenantMiddlewareTest(IamTestCase):
    """Tests against the koku tenant middleware."""

    def setUp(self):
        """Set up middleware tests."""
        super().setUp()
        self.user_data = self._create_user_data()
        self.customer = self._create_customer_data()
        self.schema_name = create_schema_name(self.customer['account_id'],
                                              self.customer['org_id'])
        self.request_context = self._create_request_context(self.customer,
                                                            self.user_data)
        request = self.request_context['request']
        request.path = '/api/v1/providers/'
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            request.user = user

    def test_get_tenant_with_user(self):
        """Test that the customer tenant is returned."""
        mock_request = self.request_context['request']
        middleware = KokuTenantMiddleware()
        result = middleware.get_tenant(Tenant, 'localhost', mock_request)
        self.assertEqual(result.schema_name, self.schema_name)

    def test_get_tenant_with_no_user(self):
        """Test that a 401 is returned."""
        mock_request = Mock(path='/api/v1/providers/', user=None)
        middleware = KokuTenantMiddleware()
        result = middleware.process_request(mock_request)
        self.assertIsInstance(result, HttpResponseUnauthorizedRequest)

    def test_get_tenant_user_not_found(self):
        """Test that a 401 is returned."""
        mock_user = Mock(username='mockuser')
        mock_request = Mock(path='/api/v1/providers/', user=mock_user)
        middleware = KokuTenantMiddleware()
        result = middleware.process_request(mock_request)
        self.assertIsInstance(result, HttpResponseUnauthorizedRequest)


class IdentityHeaderMiddlewareTest(IamTestCase):
    """Tests against the koku tenant middleware."""

    def setUp(self):
        """Set up middleware tests."""
        super().setUp()
        self.user_data = self._create_user_data()
        self.customer = self._create_customer_data()
        self.schema_name = create_schema_name(self.customer['account_id'],
                                              self.customer['org_id'])
        self.request_context = self._create_request_context(self.customer,
                                                            self.user_data,
                                                            create_customer=False)
        self.request = self.request_context['request']
        self.request.path = '/api/v1/providers/'

    def test_process_status(self):
        """Test that the request gets a user."""
        mock_request = Mock(path='/api/v1/status/')
        middleware = IdentityHeaderMiddleware()
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, 'user'))

    def test_process_not_status(self):
        """Test that the customer, tenant and user are created."""
        mock_request = self.request
        middleware = IdentityHeaderMiddleware()
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, 'user'))
        customer = Customer.objects.get(account_id=self.customer['account_id'],
                                        org_id=self.customer['org_id'])
        self.assertIsNotNone(customer)
        user = User.objects.get(username=self.user_data['username'])
        self.assertIsNotNone(user)
        tenant = Tenant.objects.get(schema_name=self.schema_name)
        self.assertIsNotNone(tenant)
