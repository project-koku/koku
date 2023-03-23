import logging
import os
import re

import sqlparse
import trino
from trino.transaction import IsolationLevel


LOG = logging.getLogger(__name__)

POSITIONAL_VARS = re.compile("%s")
NAMED_VARS = re.compile(r"%(.+)s")
EOT = re.compile(r",\s*\)$")  # pylint: disable=anomalous-backslash-in-string


class PreprocessStatementError(Exception):
    pass


class TrinoStatementExecError(Exception):
    pass


def connect(**connect_args):
    """
    Establish a trino connection.
    Keyword Params:
        schema (str) : trino schema (required)
        host (str) : trino hostname (can set from environment)
        port (int) : trino port (can set from environment)
        user (str) : trino user (can set from environment)
        catalog (str) : trino catalog (can set from enviromment)
    Returns:
        trino.dbapi.Connection : connection to trino if successful
    """
    trino_connect_args = {
        "host": (connect_args.get("host") or os.environ.get("TRINO_HOST") or os.environ.get("PRESTO_HOST") or "trino"),
        "port": (connect_args.get("port") or os.environ.get("TRINO_PORT") or os.environ.get("PRESTO_PORT") or 8080),
        "user": (connect_args.get("user") or os.environ.get("TRINO_USER") or os.environ.get("PRESTO_USER") or "admin"),
        "catalog": (
            connect_args.get("catalog")
            or os.environ.get("TRINO_DEFAULT_CATALOG")
            or os.environ.get("PRESTO_DEFAULT_CATALOG")
            or "hive"
        ),
        "isolation_level": (
            connect_args.get("isolation_level")
            or os.environ.get("TRINO_DEFAULT_ISOLATION_LEVEL")
            or os.environ.get("PRESTO_DEFAULT_ISOLATION_LEVEL")
            or IsolationLevel.AUTOCOMMIT
        ),
        "schema": connect_args["schema"],
        "legacy_primitive_types": connect_args.get("legacy_primitive_types", False),
    }
    return trino.dbapi.connect(**trino_connect_args)


def executescript(trino_conn, sqlscript, *, params=None, preprocessor=None):
    """
    Pass in a buffer of one or more semicolon-terminated trino SQL statements and it
    will be parsed into individual statements for execution. If preprocessor is None,
    then the resulting SQL and bind parameters are used. If a preprocessor is needed,
    then it should be a callable taking two positional arguments and returning a 2-element tuple:
        pre_process(sql, parameters) -> (processed_sql, processed_parameters)
    Parameters:
        trino_conn (trino.dbapi.Connection) : Connection to trino
        sqlscript (str) : Buffer of one or more semicolon-terminated SQL statements.
        params (Iterable, dict, None) : Parameters used in the SQL or None if no parameters
        preprocessor (Callable, None) : Callable taking two args and returning a 2-element tuple
                                        or None if no preprocessor is needed
    Returns:
        list : Results of each successful SQL statement executed.
    """
    all_results = []
    stmt_count = 0
    # sqlparse.split() should be a safer means to split a sql script into discrete statements
    for stmt_num, p_stmt in enumerate(sqlparse.split(sqlscript)):
        stmt_count = stmt_count + 1
        if p_stmt := str(p_stmt).strip():
            # A semicolon statement terminator is invalid in the Presto dbapi interface
            p_stmt = p_stmt.removesuffix(";")
            # This is typically for jinjasql templated sql
            if preprocessor and params:
                try:
                    stmt, s_params = preprocessor(p_stmt, params)
                except Exception as e:
                    LOG.warning(
                        f"Preprocessor Error ({e.__class__.__name__}) : {str(e)}{os.linesep}"
                        + f"Statement template : {p_stmt}"
                        + os.linesep
                        + f"Parameters : {params}"
                    )
                    exc_type = e.__class__.__name__
                    raise PreprocessStatementError(f"{exc_type} :: {e}") from e
            else:
                stmt, s_params = p_stmt, params

            try:
                cur = trino_conn.cursor()
                cur.execute(stmt, params=s_params)
                results = cur.fetchall()
            except Exception as e:
                exc_msg = (
                    f"Trino Query Error ({e.__class__.__name__}) : {str(e)} statement number {stmt_num}{os.linesep}"
                    + f"Statement: {stmt}"
                    + os.linesep
                    + f"Parameters: {s_params}"
                )
                LOG.warning(exc_msg)
                raise TrinoStatementExecError(exc_msg) from e

            all_results.extend(results)

    return all_results
