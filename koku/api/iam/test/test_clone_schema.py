#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the clone_schema functionality."""
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection as conn
from django.db import DatabaseError
from django_tenants.utils import schema_exists

from ..models import CloneSchemaFuncMissing
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
    def test_create_template_schema_exception(self):
        """
        Test that the template schema can be created directly or indirectly
        """
        Tenant.objects.filter(schema_name=Tenant._TEMPLATE_SCHEMA).delete()
        self.assertFalse(schema_exists(Tenant._TEMPLATE_SCHEMA))

        # Also validate that the template will be created using migrations
        expected = (
            "ERROR:api.iam.models:Caught exception DatabaseError during template schema create: Too Many Quatloos"
        )
        with self.assertLogs("api.iam.models", level="INFO") as _logger:
            t = Tenant(schema_name=Tenant._TEMPLATE_SCHEMA)
            t.save()
            with self.assertRaises(DatabaseError):
                with patch("api.iam.models.Tenant.create_schema", side_effect=DatabaseError("Too Many Quatloos")):
                    t._verify_template()
            self.assertIn(expected, _logger.output)
        self.assertFalse(schema_exists(Tenant._TEMPLATE_SCHEMA))

        Tenant.objects.filter(schema_name=Tenant._TEMPLATE_SCHEMA).delete()
        t = Tenant.objects.create(schema_name=Tenant._TEMPLATE_SCHEMA)
        t.save()
        t.create_schema()
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))

    def test_create_template_schema(self):
        """
        Test that the template schema can be created directly or indirectly
        """
        Tenant.objects.filter(schema_name=Tenant._TEMPLATE_SCHEMA).delete()
        self.assertFalse(schema_exists(Tenant._TEMPLATE_SCHEMA))

        # Also validate that the template will be created using migrations
        expected = f'INFO:api.iam.models:Using superclass for "{Tenant._TEMPLATE_SCHEMA}" schema creation'
        with self.assertLogs("api.iam.models", level="INFO") as _logger:
            t = Tenant(schema_name=Tenant._TEMPLATE_SCHEMA)
            t.save()
            t.create_schema()
            self.assertIn(expected, _logger.output)
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))

        Tenant.objects.filter(schema_name=Tenant._TEMPLATE_SCHEMA).delete()
        self.assertFalse(schema_exists(Tenant._TEMPLATE_SCHEMA))

        test_schema = "acct90909090"
        # Also validate that the customer tenant schema will be created using the clone function
        expected1 = f'INFO:api.iam.models:Cloning template schema "{Tenant._TEMPLATE_SCHEMA}" to "{test_schema}"'
        expected2 = f'INFO:api.iam.models:Successful clone of "{Tenant._TEMPLATE_SCHEMA}" to "{test_schema}"'
        with self.assertLogs("api.iam.models", level="INFO") as _logger:
            t = Tenant(schema_name=test_schema)
            t.save()
            t.create_schema()
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
        t = Tenant(schema_name=test_schema)
        t.save()
        t.create_schema()
        self.assertTrue(_verify_clone_func())
        self.assertTrue(schema_exists(test_schema))

    def test_tenant_object_delete_leaves_template(self):
        """
        Test that deleting a customer schema will leave the template schema untouched
        """
        cust_tenant = "acct90909093"
        self.assertFalse(schema_exists(cust_tenant))
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))

        t = Tenant(schema_name=cust_tenant)
        t.save()
        t.create_schema()
        self.assertTrue(schema_exists(cust_tenant))

        Tenant.objects.filter(schema_name=cust_tenant).delete()
        self.assertFalse(schema_exists(cust_tenant))
        self.assertTrue(schema_exists(Tenant._TEMPLATE_SCHEMA))

    def test_clone_func_create_fail(self):
        """
        Test that a failed re-application of the clone function is caught and logged
        """
        with patch("api.iam.models.Tenant._check_clone_func", return_value=False):
            with self.assertRaises(CloneSchemaFuncMissing):
                Tenant(schema_name="test_clone_func_create_fail").create_schema()

    def test_clone_schema_exception(self):
        """
        Test that a DatabaseError is raised from within the call is logged and handled
        """
        tst_schema = "test_clone_schema_exception"
        expected = 'ERROR:api.iam.models:Exception DatabaseError cloning "{}" to "{}": Too Many Quatloos'.format(
            Tenant._TEMPLATE_SCHEMA, tst_schema
        )
        with patch("api.iam.models.Tenant._clone_schema", side_effect=DatabaseError("Too Many Quatloos")):
            with self.assertLogs("api.iam.models", level="INFO") as _logger:
                with self.assertRaises(DatabaseError):
                    Tenant(schema_name=tst_schema).create_schema()
                    self.assertIn(expected, _logger.output)

    def test_create_existing_schema(self):
        """
        Test that creating an existing schema will return false and leave schema intact
        """
        raw_conn = conn.connection
        with raw_conn.cursor() as cur:
            cur.execute("""create schema if not exists "eek01";""")
            cur.execute("""create table if not exists "eek01"."tab01" (id serial primary key, data text);""")

        # Verify that the existing schema was detected
        expected = 'WARNING:api.iam.models:Schema "eek01" already exists. Exit with False.'
        with self.assertLogs("api.iam.models", level="INFO") as _logger:
            t = Tenant(schema_name="eek01")
            t.save()
            t.create_schema()
            self.assertIn(expected, _logger.output)

        # Verify that tenant record was created
        self.assertEqual(Tenant.objects.filter(schema_name="eek01").count(), 1)

        # Verify that no changes were made to existing schema
        with raw_conn.cursor() as cur:
            cur.execute("""select count(*) as ct from information_schema.tables where table_schema = 'eek01';""")
            res = cur.fetchone()[0]
            self.assertEqual(res, 1)

        # Verify that delete of tenant will also drop schema that existed
        Tenant.objects.filter(schema_name="eek01").delete()
        with raw_conn.cursor() as cur:
            cur.execute("""select count(*) from pg_namespace where nspname = 'eek01';""")
            res = cur.fetchone()[0]
            self.assertEqual(res, 0)

    def test_create_bad_tenant_name(self):
        """
        Test that creating a tenant with a bad name will throw an exception
        """

        with patch("api.iam.models.is_valid_schema_name", return_value=False):
            with self.assertRaises(ValidationError):
                t = Tenant.objects.create(schema_name="bad schema-name")
                t.create_schema()
