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
        cls.tenant = Tenant(schema_name=cls.schema_name)
        cls.tenant.save()
        cls.headers = cls.request_context['request'].META

    @classmethod
    def tearDownClass(cls):
        connection.set_schema_to_public()
        cls.tenant.delete()
        super().tearDownClass()

    @classmethod
    def _create_customer_data(cls):
        """Create customer data."""
        account = cls.fake.ean8()
        org = cls.fake.ean8()
        schema = f'acct{account}org{org}'
        customer = {'account_id': account,
                    'org_id': org,
                    'schema_name': schema}
        return customer

    @classmethod
    def _create_user_data(cls):
        """Create user data."""
        user_data = {'username': cls.fake.user_name(),
                     'email': cls.fake.email()}
        return user_data

    @classmethod
    def _create_customer(cls, account, org, create_tenant=False):
        """Create a customer.

        Args:
            account (str): The account identifier
            org (str): The organization identifier

        Returns:
            (Customer) The created customer

        """
        connection.set_schema_to_public()
        schema_name = create_schema_name(account, org)
        customer = Customer(account_id=account, org_id=org, schema_name=schema_name)
        customer.save()
        if create_tenant:
            tenant = Tenant(schema_name=schema_name)
            tenant.save()
        return customer

    @classmethod
    def _create_request_context(cls, customer_data, user_data,
                                create_customer=True, create_tenant=False):
        """Create the request context for a user."""
        customer = customer_data
        account = customer.get('account_id')
        org = customer.get('org_id')
        if create_customer:
            cls.customer = cls._create_customer(
                account,
                org,
                create_tenant=create_tenant
            )
        identity = {
            'identity': {
                'org_id': org,
                'account_number': account,
                'username': user_data['username'],
                'email': user_data['email']
            }
        }
        json_identity = json_dumps(identity)
        mock_header = b64encode(json_identity.encode('utf-8'))
        request = Mock()
        request.META = {RH_IDENTITY_HEADER: mock_header}
        request.user = user_data['username']
        request_context = {'request': request}
        return request_context
