#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test Case extension to collect common test data."""
import functools
from base64 import b64encode
from copy import deepcopy
from json import dumps as json_dumps
from unittest.mock import Mock
from uuid import UUID

import trino
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
from api.utils import DateHelper
from koku.dev_middleware import DevelopmentIdentityHeaderMiddleware
from koku.koku_test_runner import KokuTestRunner
from sources.kafka_listener import storage_callback


class FakeTrinoCur(trino.dbapi.Cursor):
    def __init__(self, *args, **kwargs):
        pass

    def execute(self, *args, **kwargs):
        pass

    def fetchall(self):
        return [["eek"]]

    @property
    def description(self):
        return []


class FakeTrinoConn(trino.dbapi.Connection):
    def __init__(self, *args, **kwargs):
        pass

    def cursor(self):
        return FakeTrinoCur()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class IamTestCase(TestCase):
    """Parent Class for IAM test cases."""

    fake = Faker()
    dh = DateHelper()

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
        cls.request_path = "/api/cost-management/v1/"

    @classmethod
    def tearDownClass(cls):
        """Tear down the class."""
        connection.set_schema_to_public()
        super().tearDownClass()

    @classmethod
    def _create_customer_data(cls, account=KokuTestRunner.account, org_id=KokuTestRunner.org_id):
        """Create customer data."""
        schema = KokuTestRunner.schema
        return {"account_id": account, "org_id": org_id, "schema_name": schema}

    @classmethod
    def _create_user_data(cls):
        """Create user data."""
        access = {
            "aws.account": {"read": ["*"]},
            "gcp.account": {"read": ["*"]},
            "gcp.project": {"read": ["*"]},
            "azure.subscription_guid": {"read": ["*"]},
            "openshift.cluster": {"read": ["*"]},
            "openshift.project": {"read": ["*"]},
            "openshift.node": {"read": ["*"]},
        }
        profile = cls.fake.simple_profile()
        return {"username": profile["username"], "email": profile["mail"], "access": access}

    @classmethod
    def _create_customer(cls, account, org_id, create_tenant=False):
        """Create a customer.

        Args:
            account (str): The account identifier

        Returns:
            (Customer) The created customer

        """
        connection.set_schema_to_public()
        schema_name = create_schema_name(org_id)
        customer = Customer.objects.get_or_create(account_id=account, org_id=org_id, schema_name=schema_name)[0]
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
        path=None,
    ):
        """Create the request context for a user."""
        customer = customer_data
        account = customer.get("account_id")
        org_id = customer.get("org_id")
        if create_customer:
            cls.customer = cls._create_customer(account, org_id, create_tenant=create_tenant)
        identity = {
            "identity": {
                "account_number": account,
                "org_id": org_id,
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
        request = Mock(path=path)
        request.META = {RH_IDENTITY_HEADER: mock_header}
        if create_user:
            tempUser = User.objects.get_or_create(
                username=user_data["username"], email=user_data["email"], customer=cls.customer
            )[0]
            tempUser.save()
            request.user = tempUser
        else:
            request.user = user_data["username"]
        return {"request": request}

    @property
    def ctx_w_path(self):
        mock_request = deepcopy(self.request_context["request"])
        mock_request.path = self.request_path
        return {"request": mock_request}

    @property
    def request_path(self):
        return self._request_path

    @request_path.setter
    def request_path(self, value):
        self._request_path = value

    def create_mock_customer_data(self, account=None, org_id=None):
        """Create randomized data for a customer test."""
        account = account or self.fake.ean8()
        org_id = org_id or self.fake.ean8()
        schema = f"org{org_id}"
        return {"account_id": account, "org_id": org_id, "schema_name": schema}

    def mocked_query_params(self, url, view, path=None, access=None):
        """Create QueryParameters using a mocked Request."""
        if access is None:
            access = {}
        m_request = self.factory.get(url)
        user = Mock()
        user.access = access
        user.customer.schema_name = self.tenant.schema_name
        m_request.user = user
        if path:
            m_request.path = path
        return QueryParameters(m_request, view)


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
                "identity": {"account_number": "10001", "org_id": "1234567", "type": "User", "user": user},
                "entitlements": {"cost_management": {"is_entitled": "True"}},
            }

            with override_settings(DEVELOPMENT=True):
                with override_settings(DEVELOPMENT_IDENTITY=identity):
                    with override_settings(FORCE_HEADER_OVERRIDE=True):
                        with override_settings(MIDDLEWARE=middleware):
                            request_context = IamTestCase._create_request_context(self.customer, user)
                            middleware = DevelopmentIdentityHeaderMiddleware()
                            middleware.process_request(request_context["request"])
                            result = function(*args, **kwargs)
            return result

        return wrapper
