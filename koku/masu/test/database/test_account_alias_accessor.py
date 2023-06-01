#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AccountAliasAccessor utility object."""
import uuid

from django_tenants.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from masu.database.account_alias_accessor import AccountAliasAccessor
from reporting.models import AWSAccountAlias


class AccountAliasAccessorTest(IamTestCase):
    """Test Cases for the AuthDBAccessor object."""

    def setUp(self):
        """Set up test cases."""
        super().setUp()

        self.account_id = self.customer_data["account_id"]

    def test_initializer(self):
        """Test Initializer."""
        accessor = AccountAliasAccessor(self.account_id, self.schema_name)
        with schema_context(self.schema_name):
            obj = accessor._get_db_obj_query().first()
        self.assertEqual(obj.account_id, self.account_id)
        self.assertEqual(obj.account_alias, self.account_id)

    def test_set_account_alias(self):
        """Test alias setter."""
        with schema_context(self.schema_name):
            AWSAccountAlias.objects.create(account_id=self.account_id, account_alias=self.account_id)

        alias_name = "test-alias"
        accessor = AccountAliasAccessor(self.account_id, self.schema_name)

        accessor.set_account_alias(alias_name)
        with schema_context(self.schema_name):
            obj = accessor._get_db_obj_query().first()
        self.assertEqual(obj.account_id, self.account_id)
        self.assertEqual(obj.account_alias, alias_name)

    def test_add_account_alias(self):
        """Test Add."""
        with schema_context(self.schema_name):
            AWSAccountAlias.objects.create(account_id=self.account_id, account_alias=self.account_id)
        accessor = AccountAliasAccessor(self.account_id, self.schema_name)

        account_id = str(uuid.uuid4())

        accessor.add(account_id)
        new_accessor = AccountAliasAccessor(account_id, self.schema_name)
        with schema_context(self.schema_name):
            obj = new_accessor._get_db_obj_query().first()

        self.assertEqual(obj.account_id, account_id)
        self.assertEqual(obj.account_alias, account_id)
