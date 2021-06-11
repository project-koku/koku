#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.db import connection as conn

from . import database as kdb
from api.iam.test.iam_test_case import IamTestCase


def execute(conn, sql, values=None):
    cur = conn.cursor()
    cur.execute(sql, values)
    return cur


class TestCheckMigrationDBFunc(IamTestCase):
    def drop_check_func(self):
        execute(conn, "drop function if exists public.app_needs_migrations(jsonb, boolean);")

    def get_public_latest_migrations(self):
        cur = execute(
            conn,
            """
select app,
       max(name) as "name"
  from public.django_migrations
 group
    by app;""",
        )
        return cur.fetchall()

    def test_migration_check_do_not_run(self):
        kdb.verify_migrations_dbfunc(conn)
        latest_migrations = self.get_public_latest_migrations()
        res = kdb.check_migrations_dbfunc(conn, latest_migrations)
        self.assertEqual(res, True)

    def test_migration_check_do_run(self):
        kdb.verify_migrations_dbfunc(conn)
        latest_migrations = self.get_public_latest_migrations()

        # Test that migrations should be run when the leaf migrations contain an app
        # that is not recorded in the database migrations tables
        latest_migrations.append(("__eek", "0999_eek_1"))
        res = kdb.check_migrations_dbfunc(conn, latest_migrations)
        self.assertEqual(res, False)

        # Test that migrations should be run when the leaf migrations are greater than
        # the latest migrations recorded in the database
        latest_migrations.pop()  # remove "__eek" app from list
        latest_migrations[0] = (latest_migrations[0][0], "0999_eek")
        res = kdb.check_migrations_dbfunc(conn, latest_migrations)
        self.assertEqual(res, False)

    def test_function_not_exists(self):
        """
        Test datbase function not found
        """
        res = kdb.dbfunc_exists(conn, "public", "___no_func_here___", "public.___no_func_here___(eek text, ook text)")
        self.assertFalse(res)

    def test_function_exists(self):
        with conn.cursor() as cur:
            cur.execute(
                """
create function public.__eek(param1 text) returns text as $BODY$
begin
    return param1;
end;
$BODY$ language plpgsql;"""
            )
            res = kdb.dbfunc_exists(conn, "public", "__eek", "public.__eek(param1 text)")
            cur.execute("""drop function public.__eek(text);""")

        self.assertTrue(res)
