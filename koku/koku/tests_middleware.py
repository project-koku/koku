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
from unittest.mock import patch

from django.core.cache import caches
from django.core.exceptions import PermissionDenied
from django.db.utils import OperationalError
from requests.exceptions import ConnectionError  # pylint: disable=W0622
from rest_framework import status

from api.iam.models import Customer
from api.iam.models import Tenant
from api.iam.models import User
from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from koku.middleware import HttpResponseUnauthorizedRequest
from koku.middleware import IdentityHeaderMiddleware
from koku.middleware import KokuTenantMiddleware


class KokuTenantMiddlewareTest(IamTestCase):
    """Tests against the koku tenant middleware."""

    def setUp(self):
        """Set up middleware tests."""
        super().setUp()
        request = self.request_context["request"]
        request.path = "/api/v1/providers/"
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            request.user = user

    def test_get_tenant_with_user(self):
        """Test that the customer tenant is returned."""
        mock_request = self.request_context["request"]
        middleware = KokuTenantMiddleware()
        result = middleware.get_tenant(Tenant, "localhost", mock_request)
        self.assertEqual(result.schema_name, self.schema_name)

    def test_get_tenant_with_no_user(self):
        """Test that a 401 is returned."""
        mock_request = Mock(path="/api/v1/providers/", user=None)
        middleware = KokuTenantMiddleware()
        result = middleware.process_request(mock_request)
        self.assertIsInstance(result, HttpResponseUnauthorizedRequest)

    def test_get_tenant_user_not_found(self):
        """Test that a 401 is returned."""
        mock_user = Mock(username="mockuser")
        mock_request = Mock(path="/api/v1/providers/", user=mock_user)
        middleware = KokuTenantMiddleware()
        result = middleware.process_request(mock_request)
        self.assertIsInstance(result, HttpResponseUnauthorizedRequest)


class IdentityHeaderMiddlewareTest(IamTestCase):
    """Tests against the koku tenant middleware."""

    def setUp(self):
        """Set up middleware tests."""
        super().setUp()
        self.request = self.request_context["request"]
        self.request.path = "/api/v1/providers/"
        self.request.META["QUERY_STRING"] = ""

    def test_process_status(self):
        """Test that the request gets a user."""
        mock_request = Mock(path="/api/v1/status/")
        middleware = IdentityHeaderMiddleware()
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, "user"))

    def test_process_not_status(self):
        """Test that the customer, tenant and user are created."""
        mock_request = self.request
        middleware = IdentityHeaderMiddleware()
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, "user"))
        customer = Customer.objects.get(account_id=self.customer.account_id)
        self.assertIsNotNone(customer)
        user = User.objects.get(username=self.user_data["username"])
        self.assertIsNotNone(user)
        tenant = Tenant.objects.get(schema_name=self.schema_name)
        self.assertIsNotNone(tenant)

    def test_process_no_customer(self):
        """Test that the customer, tenant and user are not created."""
        customer = self._create_customer_data()
        account_id = "12345"
        del customer["account_id"]
        request_context = self._create_request_context(customer, self.user_data, create_customer=False)
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/providers/"
        middleware = IdentityHeaderMiddleware()
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, "user"))
        with self.assertRaises(Customer.DoesNotExist):
            customer = Customer.objects.get(account_id=account_id)

        with self.assertRaises(User.DoesNotExist):
            User.objects.get(username=self.user_data["username"])

    def test_race_condition_customer(self):
        """Test case where another request may create the customer in a race condition."""
        customer = self._create_customer_data()
        account_id = customer["account_id"]
        orig_cust = IdentityHeaderMiddleware._create_customer(account_id)  # pylint: disable=W0212
        dup_cust = IdentityHeaderMiddleware._create_customer(account_id)  # pylint: disable=W0212
        self.assertEqual(orig_cust, dup_cust)

    def test_race_condition_user(self):
        """Test case where another request may create the user in a race condition."""
        mock_request = self.request
        middleware = IdentityHeaderMiddleware()
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, "user"))
        customer = Customer.objects.get(account_id=self.customer.account_id)
        self.assertIsNotNone(customer)
        user = User.objects.get(username=self.user_data["username"])
        self.assertIsNotNone(user)
        IdentityHeaderMiddleware._create_user(
            username=self.user_data["username"],  # pylint: disable=W0212
            email=self.user_data["email"],
            customer=customer,
            request=mock_request,
        )

    @patch("koku.rbac.RbacService.get_access_for_user")
    def test_process_non_admin(self, get_access_mock):
        """Test case for process_request as a non-admin user."""
        mock_access = {
            "aws.account": {"read": ["999999999999"]},
            "openshift.cluster": {"read": ["999999999999"]},
            "openshift.node": {"read": ["999999999999"]},
            "openshift.project": {"read": ["999999999999"]},
            "provider": {"read": ["999999999999"], "write": []},
            "rate": {"read": ["999999999999"], "write": []},
        }
        get_access_mock.return_value = mock_access

        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=False
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/providers/"
        mock_request.META["QUERY_STRING"] = ""

        middleware = IdentityHeaderMiddleware()
        middleware.process_request(mock_request)

        user_uuid = mock_request.user.uuid
        cache = caches["rbac"]
        self.assertEqual(cache.get(user_uuid), mock_access)

        middleware.process_request(mock_request)
        cache = caches["rbac"]
        self.assertEqual(cache.get(user_uuid), mock_access)

    def test_process_not_entitled(self):
        """Test that the a request cannot be made if not entitled."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=True, is_openshift=False
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/providers/"
        mock_request.META["QUERY_STRING"] = ""

        middleware = IdentityHeaderMiddleware()
        with self.assertRaises(PermissionDenied):
            middleware.process_request(mock_request)

    def test_process_malformed_header(self):
        """Test that malformed header in request results in 403."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=True, is_openshift=False
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/providers/"
        mock_request.META["HTTP_X_RH_IDENTITY"] = "not a header"

        middleware = IdentityHeaderMiddleware()
        with self.assertRaises(PermissionDenied):
            middleware.process_request(mock_request)

    def test_process_operational_error_return_424(self):
        """Test OperationalError causes 424 Reponse."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=True, is_openshift=True
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/providers/"
        mock_request.META["QUERY_STRING"] = ""

        with patch("koku.middleware.Customer.objects") as mock_customer:
            mock_customer.filter.side_effect = OperationalError

            middleware = IdentityHeaderMiddleware()
            response = middleware.process_request(mock_request)
            self.assertEqual(response.status_code, status.HTTP_424_FAILED_DEPENDENCY)

    @patch("koku.rbac.requests.get", side_effect=ConnectionError("test exception"))
    def test_rbac_connection_error_return_424(self, mocked_get):
        """Test RbacConnectionError causes 424 Reponse."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=False, is_openshift=True
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/providers/"
        mock_request.META["QUERY_STRING"] = ""

        middleware = IdentityHeaderMiddleware()
        response = middleware.process_request(mock_request)
        self.assertEqual(response.status_code, status.HTTP_424_FAILED_DEPENDENCY)
        mocked_get.assert_called()
