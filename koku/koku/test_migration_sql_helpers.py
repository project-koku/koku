import os

from django.db import connection as conn

from . import migration_sql_helpers as msh
from api.iam.test.iam_test_case import IamTestCase


class TestMigrationSQLHelpers(IamTestCase):
    def test_find_func_dir(self):
        """
        Test success finding function dir
        """
        self.assertNotEqual(msh.find_db_functions_dir(), "")

    def test_no_find_func_dir(self):
        """
        Test failure finding function dir
        """
        with self.assertRaises(FileNotFoundError):
            msh.find_db_functions_dir("___________no_dir_here_____________")

    def test_apply_sql_file(self):
        """
        Test apply sql file
        """
        filename = "./___test_apply_sql_file.sql"
        try:
            with open(filename, "wt") as f:
                print("select 1;", file=f)
            self.assertEqual(msh.apply_sql_file(conn.schema_editor(), filename), True)
        finally:
            os.unlink(filename)

    def test_no_apply_sql_file(self):
        """
        Test failure applying sql file
        """
        filename = "./___test_apply_sql_file.sql"
        try:
            with open(filename, "wt") as f:
                print("select 1;", file=f)
            with self.assertRaises(TypeError):
                msh.apply_sql_file(None, filename)
        finally:
            os.unlink(filename)

    def test_function_not_exists(self):
        """
        Test datbase function not found
        """
        res = msh.function_exists("public", "___no_func_here___", "public.___no_func_here___(eek text, ook text)")
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
            res = msh.function_exists("public", "__eek", "public.__eek(param1 text)")
            cur.execute("""drop function public.__eek(text);""")

        self.assertTrue(res)
