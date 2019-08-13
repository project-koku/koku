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
from base64 import b64encode
from json import dumps as json_dumps
from unittest.mock import Mock

from django.db import connection
from django.test import TestCase
from faker import Faker

from ..models import Customer, Tenant
from ..serializers import create_schema_name
from ...common import RH_IDENTITY_HEADER
from koku.koku_test_runner import KokuTestRunner


class IamTestCase(TestCase):
    """Parent Class for IAM test cases."""

    fake = Faker()

    @classmethod
    def setUpClass(cls):
        """Set up each test class."""
        super().setUpClass()

        cls.customer_data = cls._create_customer_data()
        cls.user_data = cls._create_user_data()
        cls.request_context = cls._create_request_context(
            cls.customer_data,
            cls.user_data
        )
        cls.schema_name = cls.customer_data.get('schema_name')
        cls.tenant = Tenant.objects.get_or_create(schema_name=cls.schema_name)[0]
        cls.tenant.save()
        cls.headers = cls.request_context['request'].META

    @classmethod
    def tearDownClass(cls):
        """Tear down the class."""
        connection.set_schema_to_public()
        # cls.tenant.delete()
        super().tearDownClass()

    @classmethod
    def _create_customer_data(cls):
        """Create customer data."""
        account = KokuTestRunner.account
        schema = KokuTestRunner.schema
        customer = {'account_id': account,
                    'schema_name': schema}
        return customer

    @classmethod
    def _create_user_data(cls):
        """Create user data."""
        user_data = {'username': cls.fake.user_name(),
                     'email': cls.fake.email()}
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
    def _create_request_context(cls, customer_data, user_data,
                                create_customer=True, create_tenant=False,
                                is_admin=True, is_hybrid_cloud=True):
        """Create the request context for a user."""
        customer = customer_data
        account = customer.get('account_id')
        if create_customer:
            cls.customer = cls._create_customer(
                account,
                create_tenant=create_tenant
            )
        identity = {
            'identity': {
                'account_number': account,
                'type': 'User',
                'user': {
                    'username': user_data['username'],
                    'email': user_data['email'],
                    'is_org_admin': is_admin
                }
            },
            'entitlements': {
                'hybrid_cloud': {'is_entitled': is_hybrid_cloud}
            }
        }
        json_identity = json_dumps(identity)
        mock_header = b64encode(json_identity.encode('utf-8'))
        request = Mock()
        request.META = {RH_IDENTITY_HEADER: mock_header}
        request.user = user_data['username']
        request_context = {'request': request}
        return request_context

    def create_mock_customer_data(self):
        """Create randomized data for a customer test."""
        account = self.fake.ean8()
        schema = f'acct{account}'
        customer = {'account_id': account,
                    'schema_name': schema}
        return customer
