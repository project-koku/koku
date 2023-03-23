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
            with open(filename, "w") as f:
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
            with open(filename, "w") as f:
                print("select 1;", file=f)
            with self.assertRaises(TypeError):
                msh.apply_sql_file(None, filename)
        finally:
            os.unlink(filename)
