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

    def test_migration_check_dbfunc_exists(self):
        func_sig = "public.app_needs_migrations(leaf_migrations jsonb, _verbose boolean DEFAULT false)"
        self.drop_check_func()
        res = kdb.dbfunc_exists(conn, func_sig)
        self.assertEqual(res, False)

        kdb.install_migrations_dbfunc(conn)
        res = kdb.dbfunc_exists(conn, func_sig)
        self.assertEqual(res, True)

    def test_migration_check_do_not_run(self):
        kdb.verify_migrations_dbfunc(conn)
        latest_migrations = self.get_public_latest_migrations()
        res = kdb.check_migrattions_dbfunc(conn, latest_migrations)
        self.assertEqual(res, True)

    def test_migration_check_do_run(self):
        kdb.verify_migrations_dbfunc(conn)
        latest_migrations = self.get_public_latest_migrations()

        # Test that migrations should be run when the leaf migrations contain an app
        # that is not recorded in the database migrations tables
        latest_migrations.append(("__eek", "0999_eek_1"))
        res = kdb.check_migrattions_dbfunc(conn, latest_migrations)
        self.assertEqual(res, False)

        # Test that migrations should be run when the leaf migrations are greater than
        # the latest migrations recorded in the database
        latest_migrations.pop()  # remove "__eek" app from list
        latest_migrations[0] = (latest_migrations[0][0], "0999_eek")
        res = kdb.check_migrattions_dbfunc(conn, latest_migrations)
        self.assertEqual(res, False)
