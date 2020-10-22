#
# Copyright 2020 Red Hat, Inc.
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
"""Test the IAM serializers."""
from django.db import connection as conn
from tenant_schemas.utils import schema_exists

from ..models import CloneSchemaTemplateMissing
from ..models import Tenant
from .iam_test_case import IamTestCase
from koku.database import dbfunc_exists


_CLONE_FUNC_SCHEMA = Tenant._CLONE_SCHEMA_FUNC_SCHEMA
_CLONE_FUNC_SIG = Tenant._CLONE_SCHEMA_FUNC_SIG
_CLONE_FUNC_NAME = Tenant._CLONE_SHEMA_FUNC_NAME


def _verify_clone_func():
    return dbfunc_exists(conn, _CLONE_FUNC_SCHEMA, _CLONE_FUNC_NAME, _CLONE_FUNC_SIG)


def _drop_clone_func():
    sql = f"""
drop function if exists {_CLONE_FUNC_SIG.replace(' DEFAULT false', '')} ;
"""
    with conn.cursor() as cur:
        cur.execute(sql, None)


def _drop_template_schema():
    sql = f"""
drop schema if exists {Tenant._TEMPLATE_SCHEMA} cascade ;
"""
    with conn.cursor() as cur:
        cur.execute(sql, None)


def _delete_tenant_record():
    sql = """
delete
  from public.api_tenant
 where schema_name = %s ;
"""
    with conn.cursor() as cur:
        cur.execute(sql, (Tenant._TEMPLATE_SCHEMA,))


class CloneSchemaTest(IamTestCase):
    def test_create_template_schema(self):
        """
        Test that the template schema can be created directly or indirectly
        """
        Tenant.objects.filter(schema_name=Tenant._TEMPLATE_SCHEMA).delete()
        self.assertFalse(schema_exists(Tenant._TEMPLATE_SCHEMA))

        # Also validate that the template will be created using migrations
        expected = f'INFO:api.iam.models:Using superclass for "{Tenant._TEMPLATE_SCHEMA}" schema creation'
        with self.assertLogs("api.iam.models", level="INFO") as _logger:
            Tenant(schema_name=Tenant._TEMPLATE_SCHEMA).save()
            self.assertIn(expected, _logger.output)
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))

        Tenant.objects.filter(schema_name=Tenant._TEMPLATE_SCHEMA).delete()
        self.assertFalse(schema_exists(Tenant._TEMPLATE_SCHEMA))

        test_schema = "acct90909090"
        # Also validate that the customer tenant schema will be created using the clone function
        expected1 = (
            f'INFO:api.iam.models:Cloning template schema "{Tenant._TEMPLATE_SCHEMA}" to "{test_schema}" with data'
        )
        expected2 = f'INFO:api.iam.models:Successful clone of "{Tenant._TEMPLATE_SCHEMA}" to "{test_schema}"'
        with self.assertLogs("api.iam.models", level="INFO") as _logger:
            Tenant(schema_name=test_schema).save()
            self.assertIn(expected1, _logger.output)
            self.assertIn(expected2, _logger.output)
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))
        self.assertTrue(schema_exists(test_schema))

    def test_clone_schema_missing_clone_func(self):
        """
        Test that the clone function will be applied if it is missing and the clone will succeed
        """
        _drop_clone_func()
        self.assertFalse(_verify_clone_func())

        test_schema = "acct90909091"
        self.assertFalse(schema_exists(test_schema))
        Tenant(schema_name=test_schema).save()
        self.assertTrue(_verify_clone_func())
        self.assertTrue(schema_exists(test_schema))

    def test_has_template_rec_missing_template_schema(self):
        """
        Test that am existing template tenant record with a missing tenant schema will throw an exception
        """
        _drop_template_schema()
        self.assertFalse(schema_exists(Tenant._TEMPLATE_SCHEMA))

        test_schema = "acct90909092"
        with self.assertRaises(CloneSchemaTemplateMissing):
            Tenant(schema_name=test_schema).save()

        Tenant.objects.filter(schema_name=Tenant._TEMPLATE_SCHEMA).delete()
        Tenant(schema_name=test_schema).save()
        self.assertTrue(schema_exists(test_schema))
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))

    def test_tenant_object_delete_leaves_template(self):
        """
        Test that deleting a customer schema will leave the template schema untouched
        """
        cust_tenant = "acct90909093"
        self.assertFalse(schema_exists(cust_tenant))
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))

        Tenant(schema_name=cust_tenant).save()
        self.assertTrue(schema_exists(cust_tenant))

        Tenant.objects.filter(schema_name=cust_tenant).delete()
        self.assertFalse(schema_exists(cust_tenant))
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))
