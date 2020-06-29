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
"""Test Case extension to collect common test data."""
import functools
from base64 import b64encode
from json import dumps as json_dumps
from unittest.mock import Mock
from uuid import UUID

from django.conf import settings
from django.db import connection
from django.db.models.signals import post_save
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase
from faker import Faker

from api.common import RH_IDENTITY_HEADER
from api.iam.serializers import create_schema_name
from api.models import Customer
from api.models import Tenant
from api.models import User
from api.provider.models import Sources
from api.query_params import QueryParameters
from koku.dev_middleware import DevelopmentIdentityHeaderMiddleware
from koku.koku_test_runner import KokuTestRunner
from sources.kafka_listener import storage_callback


class IamTestCase(TestCase):
    """Parent Class for IAM test cases."""

    fake = Faker()

    @classmethod
    def setUpClass(cls):
        """Set up each test class."""
        super().setUpClass()
        post_save.disconnect(storage_callback, sender=Sources)

        cls.customer_data = cls._create_customer_data()
        cls.user_data = cls._create_user_data()
        cls.request_context = cls._create_request_context(cls.customer_data, cls.user_data)
        cls.schema_name = cls.customer_data.get("schema_name")
        cls.tenant = Tenant.objects.get_or_create(schema_name=cls.schema_name)[0]
        cls.tenant.save()
        cls.headers = cls.request_context["request"].META
        cls.provider_uuid = UUID("00000000-0000-0000-0000-000000000001")
        cls.factory = RequestFactory()

    @classmethod
    def tearDownClass(cls):
        """Tear down the class."""
        connection.set_schema_to_public()
        super().tearDownClass()

    @classmethod
    def _create_customer_data(cls, account=KokuTestRunner.account):
        """Create customer data."""
        schema = KokuTestRunner.schema
        customer = {"account_id": account, "schema_name": schema}
        return customer

    @classmethod
    def _create_user_data(cls):
        """Create user data."""
        access = {
            "aws.account": {"read": ["*"]},
            "azure.subscription_guid": {"read": ["*"]},
            "openshift.cluster": {"read": ["*"]},
            "openshift.project": {"read": ["*"]},
            "openshift.node": {"read": ["*"]},
        }
        user_data = {"username": cls.fake.user_name(), "email": cls.fake.email(), "access": access}
        return user_data

    @classmethod
    def _create_customer(cls, account, create_tenant=False):
        """Create a customer.

        Args:
            account (str): The account identifier

        Returns:
            (Customer) The created customer

        """
        connection.set_schema_to_public()
        schema_name = create_schema_name(account)
        customer = Customer.objects.get_or_create(account_id=account, schema_name=schema_name)[0]
        customer.save()
        if create_tenant:
            tenant = Tenant.objects.get_or_create(schema_name=schema_name)[0]
            tenant.save()
        return customer

    @classmethod
    def _create_request_context(
        cls,
        customer_data,
        user_data,
        create_customer=True,
        create_user=True,
        create_tenant=False,
        is_admin=True,
        is_cost_management=True,
    ):
        """Create the request context for a user."""
        customer = customer_data
        account = customer.get("account_id")
        if create_customer:
            cls.customer = cls._create_customer(account, create_tenant=create_tenant)
        identity = {
            "identity": {
                "account_number": account,
                "type": "User",
                "user": {
                    "username": user_data["username"],
                    "email": user_data["email"],
                    "is_org_admin": is_admin,
                    "access": user_data["access"],
                },
            },
            "entitlements": {"cost_management": {"is_entitled": is_cost_management}},
        }
        json_identity = json_dumps(identity)
        mock_header = b64encode(json_identity.encode("utf-8")).decode("utf-8")
        request = Mock()
        request.META = {RH_IDENTITY_HEADER: mock_header}
        if create_user:
            tempUser = User(username=user_data["username"], email=user_data["email"], customer=cls.customer)
            tempUser.save()
            request.user = tempUser
        else:
            request.user = user_data["username"]
        request_context = {"request": request}
        return request_context

    def create_mock_customer_data(self):
        """Create randomized data for a customer test."""
        account = self.fake.ean8()
        schema = f"acct{account}"
        customer = {"account_id": account, "schema_name": schema}
        return customer

    def mocked_query_params(self, url, view, path=None):
        """Create QueryParameters using a mocked Request."""
        m_request = self.factory.get(url)
        user = Mock()
        user.access = None
        user.customer.schema_name = self.tenant.schema_name
        m_request.user = user
        if path:
            m_request.path = path
        query_params = QueryParameters(m_request, view)
        return query_params


class RbacPermissions:
    """A decorator class for running tests with a custom identity.

    Example usage:

        @RbacPermissions({"openshift.cluster": {"read": ["*"]}})
        def my_unit_test(self):
            your_test_code = here()

    """

    def __init__(self, access):
        """Class constructor."""
        self.access = access
        self.customer = IamTestCase._create_customer_data()
        self.user = IamTestCase._create_user_data()

    def __call__(self, function):
        """Call method."""

        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            user = self.user
            user["access"] = self.access

            dev_middleware = "koku.dev_middleware.DevelopmentIdentityHeaderMiddleware"
            middleware = settings.MIDDLEWARE
            if dev_middleware not in middleware:
                middleware.insert(5, dev_middleware)

            identity = {
                "identity": {"account_number": "10001", "type": "User", "user": user},
                "entitlements": {"cost_management": {"is_entitled": "True"}},
            }

            with override_settings(DEVELOPMENT=True):
                with override_settings(DEVELOPMENT_IDENTITY=identity):
                    with override_settings(MIDDLEWARE=middleware):
                        request_context = IamTestCase._create_request_context(self.customer, user)
                        middleware = DevelopmentIdentityHeaderMiddleware()
                        middleware.process_request(request_context["request"])
                        result = function(*args, **kwargs)
            return result

        return wrapper
