#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import os

from django.db.backends.base.schema import BaseDatabaseSchemaEditor


LOG = logging.getLogger(__name__)


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
    with open(path) as file:
        sqlbuff = file.read()

    if literal_placeholder:
        sqlbuff = sqlbuff.replace("%", "%%")

    if isinstance(conn, BaseDatabaseSchemaEditor):
        try:
            conn.execute(sqlbuff)
        except Exception as e:  # Log statement buffer on *any* exception
            LOG.error(f"Error {e.__class__.__name__} applying SQL buffer: {os.linesep}{sqlbuff}")
            raise e
    else:
        raise TypeError(f'Cannot apply SQL file "{path}" with instance of "{conn.__class__.__name__}"')

    return True
