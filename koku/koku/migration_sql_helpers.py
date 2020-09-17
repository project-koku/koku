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
import os

from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def find_db_functions_dir(db_func_dir_name="db_functions"):
    """
    Find the directory in the project path that contains the database functions.
    Params:
        db_func_dir_name (str) : name of the directory containing the SQL function files
    Returns:
        (str) : Directory path including the function dir name
    """
    path = os.path.dirname(os.path.abspath(__file__))
    while True:
        if db_func_dir_name not in os.listdir(path):
            if path == os.path.sep:
                raise FileNotFoundError("Could not find the db_functions dir")
            path = os.path.dirname(path)
        else:
            path = os.path.join(path, db_func_dir_name)
            break

    return path


def apply_sql_file(conn, path, literal_placeholder=False):
    """
    Reads the contents of the given SQL file and passes the buffer to the executor
    for application to the database.
    Params:
        conn (BaseDatabaseSchemaEditor) : DB executor
        path (str) : Path to the SQL file to apply
    Returns:
        True
    """
    sqlbuff = open(path, "rt").read()
    if literal_placeholder:
        sqlbuff = sqlbuff.replace("%", "%%")
    if isinstance(conn, BaseDatabaseSchemaEditor):
        conn.execute(sqlbuff)
    else:
        raise TypeError(f'Cannot apply SQL file "{path}" with instance of "{conn.__class__.__name__}"')

    return True
