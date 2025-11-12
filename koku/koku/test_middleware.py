#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the project middleware."""
import base64
import copy
import json
import logging
import time
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from cachetools import TTLCache
from django.core.cache import caches
from django.core.exceptions import PermissionDenied
from django.db.utils import IntegrityError
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.test.utils import override_settings
from django.urls import reverse
from faker import Faker
from requests.exceptions import ConnectionError
from rest_framework import status
from rest_framework.test import APIClient

from api.common import RH_IDENTITY_HEADER
from api.iam.models import Customer
from api.iam.models import Tenant
from api.iam.models import User
from api.iam.test.iam_test_case import IamTestCase
from koku import middleware as MD
from koku.cache import CacheEnum
from koku.middleware import HttpResponseUnauthorizedRequest
from koku.middleware import IdentityHeaderMiddleware
from koku.middleware import KokuTenantMiddleware
from koku.middleware import KokuTenantSchemaExistsMiddleware
from koku.middleware import RequestTimingMiddleware
from koku.test_rbac import mocked_requests_get_500_text


class KokuTenantSchemaExistsMiddlewareTest(IamTestCase):
    def test_process_exception_empty_response(self):
        """Assert that an exception raised for a non-existent Tenant returns empty result set."""
        mock_request = MagicMock(user=Mock(customer=Mock(schema_name="nope")))
        result = KokuTenantSchemaExistsMiddleware(Mock()).process_exception(mock_request, Exception())
        self.assertIsInstance(result, JsonResponse)

    def test_process_exception_not_empty_response(self):
        """Assert that an exception raised for a valid tenant does not return emtpy result set."""
        mock_request = self.request_context["request"]
        result = KokuTenantSchemaExistsMiddleware(Mock()).process_exception(mock_request, Exception())
        self.assertIsNone(result)


class KokuTenantMiddlewareTest(IamTestCase):
    """Tests against the koku tenant middleware."""

    def setUp(self):
        """Set up middleware tests."""
        super().setUp()
        self.request = copy.deepcopy(self.request_context["request"])
        self.request.path = "/api/v1/tags/aws/"
        mock_get_response = Mock()
        self.middleware = KokuTenantMiddleware(mock_get_response)

    def test_get_tenant_from_cache(self):
        """Test that a tenant is returned when exists in tenant_cache"""
        tenant = MagicMock()
        tenant.schema_name = self.schema_name
        mock_request = self.request
        tenant_username = mock_request.user.username
        KokuTenantMiddleware.tenant_cache[tenant_username] = tenant

        with patch("koku.middleware.KokuTenantMiddleware.tenant_cache.get") as mock_cache_get:
            mock_cache_get.return_value = tenant
            result = self.middleware._get_tenant(mock_request)

        self.assertEqual(result, tenant)
        self.assertEqual(result.schema_name, tenant.schema_name)

    def test_get_tenant_from_db(self):
        """Test that a tenant is returned when exists in Tenant database"""
        mock_request = self.request
        result = self.middleware._get_tenant(mock_request)
        self.assertIsNotNone(result)
        self.assertEqual(result.schema_name, self.schema_name)

    def test_get_tenant_with_no_user(self):
        """Test that a 401 is returned."""
        mock_request = self.request
        mock_request.user = None
        result = self.middleware.process_request(mock_request)
        self.assertIsInstance(result, HttpResponseUnauthorizedRequest)

    def test_get_tenant_user_not_found(self):
        """Test that a 401 is returned."""
        mock_user = Mock(spec=["not-username"])
        mock_request = Mock(path="/api/v1/tags/aws/", user=mock_user)
        result = self.middleware.process_request(mock_request)
        self.assertIsInstance(result, HttpResponseUnauthorizedRequest)

    @patch("koku.rbac.RbacService.get_access_for_user")
    def test_process_request_user_access_no_permissions(self, get_access_mock):
        """Test PermissionDenied is not raised for user-access calls"""
        get_access_mock.return_value = {}
        mock_request = self.request
        mock_request.path = reverse("user-access")
        try:
            self.middleware.process_request(mock_request)
        except PermissionDenied:
            self.fail("test raised PermissionDenied")

    @patch("koku.rbac.RbacService.get_access_for_user")
    def test_process_request_denied(self, get_access_mock):
        """Test PermissionDenied is raised for non-user-access calls"""
        get_access_mock.return_value = {}
        mock_request = self.request
        with self.assertRaises(PermissionDenied):
            _ = self.middleware.process_request(mock_request)

    @patch("koku.middleware.KokuTenantMiddleware.tenant_cache", TTLCache(5, 1))
    def test_tenant_caching(self):
        """Test that the tenant cache is successfully storing and expiring."""
        # Check that the cache is initially empty
        self.assertEqual(KokuTenantMiddleware.tenant_cache.currsize, 0)

        mock_request = self.request
        self.middleware._get_tenant(mock_request)

        self.assertEqual(KokuTenantMiddleware.tenant_cache.currsize, 1)
        time.sleep(1.1)  # Wait more than the ttl
        self.assertEqual(KokuTenantMiddleware.tenant_cache.currsize, 0)


class IdentityHeaderMiddlewareTest(IamTestCase):
    """Tests against the koku tenant middleware."""

    def setUp(self):
        """Set up middleware tests."""
        super().setUp()
        self.request = self.request_context["request"]
        self.request.path = "/api/v1/tags/aws/"
        self.request.META["QUERY_STRING"] = ""
        self.mock_get_response = Mock()

    def test_process_status(self):
        """Test that the request gets a user."""
        mock_request = Mock(path="/api/v1/status/")
        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, "user"))

    def test_process_not_status(self):
        """Test that the customer, tenant and user are created."""
        mock_request = self.request
        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, "user"))
        customer = Customer.objects.get(account_id=self.customer.account_id)
        self.assertIsNotNone(customer)
        user = User.objects.get(username=self.user_data["username"])
        self.assertIsNotNone(user)
        tenant = Tenant.objects.get(schema_name=self.schema_name)
        self.assertIsNotNone(tenant)

    @patch("koku.middleware.IdentityHeaderMiddleware.customer_cache", TTLCache(5, 0.1))
    @patch("koku.middleware.USER_CACHE", TTLCache(5, 0.1))
    def test_process_not_status_caching(self):
        """Test that the customer, tenant and user are created and cached"""
        mock_request = self.request
        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        self.assertEqual(MD.USER_CACHE.currsize, 0)
        self.assertEqual(MD.USER_CACHE.maxsize, 5)  # Confirm that the size of the mocked user cache has been updated
        self.assertEqual(IdentityHeaderMiddleware.customer_cache.currsize, 0)
        middleware.process_request(mock_request)  # Adds 1 to the customer and user cache
        self.assertTrue(hasattr(mock_request, "user"))
        self.assertEqual(IdentityHeaderMiddleware.customer_cache.currsize, 1)
        self.assertEqual(MD.USER_CACHE.currsize, 1)
        middleware.process_request(mock_request)  # make the same request again and do not see any cache changes
        self.assertEqual(IdentityHeaderMiddleware.customer_cache.currsize, 1)
        self.assertEqual(MD.USER_CACHE.currsize, 1)
        customer = Customer.objects.get(account_id=self.customer.account_id)
        self.assertIsNotNone(customer)
        user = User.objects.get(username=self.user_data["username"])
        self.assertIsNotNone(user)
        time.sleep(0.2)  # Wait for the ttl
        self.assertEqual(IdentityHeaderMiddleware.customer_cache.currsize, 0)
        self.assertEqual(MD.USER_CACHE.currsize, 0)

    def test_process_no_customer(self):
        """Test that the customer, tenant and user are not created."""
        customer = self._create_customer_data()
        user_data = self._create_user_data()
        account_id = "99999"
        del customer["account_id"]
        del customer["org_id"]
        request_context = self._create_request_context(customer, user_data, create_customer=False, create_user=False)
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, "user"))
        with self.assertRaises(Customer.DoesNotExist):
            customer = Customer.objects.get(account_id=account_id)

        with self.assertRaises(User.DoesNotExist):
            User.objects.get(username=user_data["username"])

    def test_process_customer_new_account_id(self):
        """Test that a customer that later recieves an account_id is updated appropriately."""
        org_id = "88888"
        account_id = "88888888"
        # create customer initially without an account_id
        customer = self._create_customer_data(account=None, org_id=org_id)
        user_data = self._create_user_data()
        request_context = self._create_request_context(customer, user_data, create_customer=True, create_user=False)
        mock_request = request_context["request"]
        mock_request.META["QUERY_STRING"] = ""
        mock_request.path = "/api/v1/tags/aws/"
        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)
        self.assertTrue(hasattr(mock_request, "user"))
        customer = Customer.objects.get(org_id=org_id)
        self.assertIsNone(customer.account_id)

        # send another request with the new account_id and ensure it is updated
        customer = self._create_customer_data(account=account_id, org_id=org_id)
        request_context = self._create_request_context(customer, user_data, create_customer=False, create_user=False)
        mock_request = request_context["request"]
        mock_request.META["QUERY_STRING"] = ""
        mock_request.path = "/api/v1/tags/aws/"
        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)
        customer = Customer.objects.get(org_id=org_id)
        self.assertEqual(customer.account_id, account_id)

    def test_race_condition_customer(self):
        """Test case where another request may create the customer in a race condition."""
        customer = self._create_customer_data()
        account_id = customer["account_id"]
        org_id = customer["org_id"]
        orig_cust = IdentityHeaderMiddleware.create_customer(account_id, org_id, "POST")
        dup_cust = IdentityHeaderMiddleware.create_customer(account_id, org_id, "POST")
        self.assertEqual(orig_cust, dup_cust)

    @override_settings(CACHES={CacheEnum.rbac: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    @patch("koku.rbac.RbacService.get_access_for_user")
    def test_process_non_admin(self, get_access_mock):
        """Test case for process_request as a non-admin user."""
        mock_access = {
            "aws.account": {"read": ["999999999999"]},
            "gcp.account": {"read": ["999999999999"]},
            "gcp.project": {"read": ["999999999999"]},
            "openshift.cluster": {"read": ["999999999999"]},
            "openshift.node": {"read": ["999999999999"]},
            "openshift.project": {"read": ["999999999999"]},
            "provider": {"read": ["999999999999"], "write": []},
            "cost_model": {"read": ["999999999999"], "write": []},
        }
        get_access_mock.return_value = mock_access

        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=False
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        mock_request.META["QUERY_STRING"] = ""

        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)

        user_uuid = mock_request.user.uuid
        org_id = customer.get("org_id")
        cache = caches[CacheEnum.rbac]
        cache_key = f"{user_uuid}_{org_id}"
        self.assertEqual(cache.get(cache_key), mock_access)

        middleware.process_request(mock_request)
        cache = caches[CacheEnum.rbac]
        self.assertEqual(cache.get(cache_key), mock_access)

    def test_process_not_entitled(self):
        """Test that the a request cannot be made if not entitled."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=True, is_cost_management=False
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        mock_request.META["QUERY_STRING"] = ""

        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        with self.assertRaises(PermissionDenied):
            middleware.process_request(mock_request)

    def test_process_malformed_header(self):
        """Test that malformed header in request results in 403."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=True, is_cost_management=False
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        mock_request.META["HTTP_X_RH_IDENTITY"] = "not a header"

        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        with self.assertRaises(PermissionDenied):
            middleware.process_request(mock_request)

    def test_process_beta_url_path(self):
        """Test that user beta flag is True for beta url path."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=True, is_cost_management=True
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        mock_request.META["QUERY_STRING"] = ""
        mock_request.META["HTTP_REFERER"] = "http://cost.com/beta/report"

        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)
        self.assertTrue(mock_request.user.beta)

    def test_process_non_beta_url_path(self):
        """Test that user non-beta flag is False for beta url path."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=True, is_cost_management=True
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        mock_request.META["QUERY_STRING"] = ""
        mock_request.META["HTTP_REFERER"] = "http://cost.com/report"

        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)
        self.assertFalse(mock_request.user.beta)

    @patch("koku.middleware.IdentityHeaderMiddleware.customer_cache", TTLCache(5, 3))
    def test_process_operational_error_return_424(self):
        """Test OperationalError causes 424 Reponse."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=True, is_cost_management=True
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        mock_request.META["QUERY_STRING"] = ""

        with patch("koku.middleware.Customer.objects") as mock_customer:
            mock_customer.filter.side_effect = OperationalError

            middleware = IdentityHeaderMiddleware(self.mock_get_response)
            response = middleware.process_request(mock_request)
            self.assertEqual(response.status_code, status.HTTP_424_FAILED_DEPENDENCY)

    @patch("koku.rbac.requests.get", side_effect=ConnectionError("test exception"))
    def test_rbac_connection_error_return_424(self, mocked_get):
        """Test RbacConnectionError causes 424 Reponse."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=False, is_cost_management=True
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        mock_request.META["QUERY_STRING"] = ""

        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        response = middleware.process_request(mock_request)
        self.assertEqual(response.status_code, status.HTTP_424_FAILED_DEPENDENCY)
        mocked_get.assert_called()

    @patch("koku.rbac.requests.get", side_effect=mocked_requests_get_500_text)
    def test_rbac_500_response_return_424(self, mocked_get):
        """Test 500 RBAC response causes 424 Reponse."""
        user_data = self._create_user_data()
        customer = self._create_customer_data()
        request_context = self._create_request_context(
            customer, user_data, create_customer=True, create_tenant=True, is_admin=False, is_cost_management=True
        )
        mock_request = request_context["request"]
        mock_request.path = "/api/v1/tags/aws/"
        mock_request.META["QUERY_STRING"] = ""

        middleware = IdentityHeaderMiddleware(self.mock_get_response)

        response = middleware.process_request(mock_request)
        self.assertEqual(response.status_code, status.HTTP_424_FAILED_DEPENDENCY)
        mocked_get.assert_called()

    @override_settings(DEVELOPMENT=True)
    def test_process_developer_identity(self):
        """Test that process_request() passes-through a custom identity."""
        fake = Faker()

        identity = {
            "identity": {
                "account_number": str(fake.pyint()),
                "org_id": str(fake.pyint()),
                "type": "User",
                "user": {
                    "username": fake.word(),
                    "email": fake.email(),
                    "is_org_admin": False,
                    "access": {
                        "aws.account": {"read": ["1234567890AB", "234567890AB1"]},
                        "azure.subscription_guid": {"read": ["*"]},
                    },
                },
            },
            "entitlements": {"cost_management": {"is_entitled": True}},
        }

        mock_request = Mock(path="/api/v1/reports/azure/costs/", META={"QUERY_STRING": ""})

        user = Mock(
            access={
                "aws.account": {"read": ["1234567890AB", "234567890AB1"]},
                "azure.subscription_guid": {"read": ["*"]},
            },
            username=fake.word(),
            email=fake.email(),
            admin=False,
            customer=Mock(account_id=fake.pyint()),
            req_id="DEVELOPMENT",
        )

        mock_request.user = user
        mock_request.META[RH_IDENTITY_HEADER] = base64.b64encode(json.dumps(identity).encode("utf-8"))

        logging.disable(logging.NOTSET)
        with self.assertLogs(logger="koku.middleware", level=logging.WARNING):
            middleware = IdentityHeaderMiddleware(self.mock_get_response)
            middleware.process_request(mock_request)

    @override_settings(DEVELOPMENT=True)
    def test_process_service_account_identity(self):
        """Test that process_request() passes-through a custom identity."""
        fake = Faker()

        identity = {
            "identity": {
                "account_number": str(fake.pyint()),
                "org_id": str(fake.pyint()),
                "type": "ServiceAccount",
                "service_account": {
                    "username": fake.word(),
                    "client_id": fake.word(),
                },
            },
            "entitlements": {"cost_management": {"is_entitled": True}},
        }

        mock_request = Mock(path="/api/v1/reports/azure/costs/", META={"QUERY_STRING": ""})

        user = Mock(
            access={
                "aws.account": {"read": ["1234567890AB", "234567890AB1"]},
                "azure.subscription_guid": {"read": ["*"]},
            },
            username=fake.word(),
            email="",
            admin=False,
            customer=Mock(account_id=fake.pyint()),
            req_id="DEVELOPMENT",
        )

        mock_request.user = user
        mock_request.META[RH_IDENTITY_HEADER] = base64.b64encode(json.dumps(identity).encode("utf-8"))
        middleware = IdentityHeaderMiddleware(self.mock_get_response)
        middleware.process_request(mock_request)

    @patch("api.iam.models.Customer.save")
    def test_create_customer(self, mock_save):
        """Test creating a customer."""

        mock_save.return_value = None
        customer = IdentityHeaderMiddleware.create_customer("test_account", "test_org", "POST")

        self.assertIsNotNone(customer)
        self.assertEqual(customer.account_id, "test_account")
        mock_save.assert_called_once()

    @patch("api.iam.models.Customer.objects.filter")
    @patch("api.iam.models.Customer.save", side_effect=IntegrityError)
    def test_create_customer_integrity_error_existing_customer(self, mock_save, mock_filter):
        """Test fetching an  existing customer when an IntegrityError occurs."""

        mock_query_set = MagicMock()
        mock_filter.return_value = mock_query_set
        mock_query_set.get.return_value = MagicMock(account_id="test_account", org_id="test_org")

        customer = IdentityHeaderMiddleware.create_customer("test_account", "test_org", "POST")

        self.assertIsNotNone(customer)
        mock_save.assert_called_once()
        self.assertEqual(customer.org_id, "test_org")
        mock_filter.assert_called_once_with(org_id="test_org")


class RequestTimingMiddlewareTest(IamTestCase):
    """Tests against the koku tenant middleware."""

    def setUp(self):
        """Set up middleware tests."""
        super().setUp()
        self.request = self.request_context["request"]
        self.request.path = "/api/v1/status/"
        self.request.META["QUERY_STRING"] = ""

    def test_process_request(self):
        """Test that the request gets a user."""
        mock_get_response = Mock()
        middleware = RequestTimingMiddleware(mock_get_response)
        middleware.process_request(self.request)
        self.assertTrue(hasattr(self.request, "start_time"))

    @patch("koku.middleware.KokuTenantMiddleware._get_tenant")
    def test_process_response(self, mock_get_tenant):
        """Test that the request gets a user."""

        mock_get_tenant.return_value = self.tenant
        client = APIClient()
        url = reverse("server-status")
        with self.assertLogs(logger="koku.middleware", level="INFO") as logger:
            client.get(url, **self.headers)
            output = logger.output
            logged = False
            for msg in output:
                if "response_time" in msg:
                    logged = True
            self.assertTrue(logged)
