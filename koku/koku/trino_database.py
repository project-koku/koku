import logging
import os
import re
from decimal import Decimal

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


def _type_transform(v):
    """
    Simple transform to change various Python types to a PrestoSQL token for
    insert into a statement. No casts are emitted.
    Params:
        v (various) : Query parameter value
    Returns:
        str : Proper string representation of value for a PrestoSQL query.
    """
    if v is None:
        # convert None to keyword null
        return "null"
    elif isinstance(v, (int, float, Decimal, complex, bool, list)):
        # Convert to string without surrounding quotes making a bare token
        return str(v)
    elif isinstance(v, tuple):
        # Convert to string without surrounding quotes making a bare token
        # Also convert (val,) to (val) for length 1 tuples
        return EOT.sub(")", str(v))
    else:
        # Convert to string *with* surrounding single-quote characters
        return f"'{str(v)}'"


def _has_params(sql):
    """
    Detect parameter substitution tokens in a PrestoSQL statement
    Params:
        sql (str) : PrestoSQL statement
    Returns:
        bool : True if substitution tokens found else False
    """
    return bool(POSITIONAL_VARS.search(sql)) or bool(NAMED_VARS.search(sql))


def sql_mogrify(sql, params=None):
    """
    Cheap version of psycopg2.Cursor.mogrify method. Does not inject type casting.
    None type will be converted to "null"
    int, float, Decimal, complex, bool, list, tuple types will be converted to string
    All other types will be converted to strings surrounded by single-quote characters
    Params:
        sql (str) : SQL formatted for the driver using %s or %(name)s placeholders
        params (list, tuple, dict) : Parameter values
    Returns:
        str : SQL statement with parameter values substituted
    """
    if params is not None and _has_params(sql):
        if isinstance(params, dict):
            mog_params = {k: _type_transform(v) for k, v in params.items()}
        else:
            mog_params = tuple(_type_transform(p) for p in params)

        return sql % mog_params
    else:
        return sql


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
    presto_connect_args = {
        "host": (
            connect_args.get("host") or os.environ.get("TRINO_HOST") or os.environ.get("PRESTO_HOST") or "presto"
        ),
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
    }
    conn = trino.dbapi.connect(**presto_connect_args)
    return conn


def _fetchall(presto_cur):
    """
    Wrapper around the trino.dbapi.Cursor.fetchall() method
    Params:
        presto_cur (presto.dbapi.Cursor) : Presto cursor that has already called the execute method
    Returns:
        list : Results of cursor execution and results fetch
    """
    return presto_cur.fetchall()


def _cursor(presto_conn):
    """
    Wrapper around the trino.dbapi.Connection.cursor() method
    Params:
        presto_conn (trino.dbapi.Connection) Active presto connection
    Returns:
        trino.dbapi.Cursor : Cursor for the connection
    """
    return presto_conn.cursor()


def _execute(presto_cur, presto_stmt):
    """
    Wrapper around the trino.dbapi.Cursor.execute() method
    Params:
        presto_cur (trino.dbapi.Cursor) : presto connection cursor
        presto_stmt (str) : presto SQL statement
    Returns:
        trino.dbapi.Cursor : Cursor after execute method called
    """
    presto_cur.execute(presto_stmt)
    return presto_cur


def execute(presto_conn, sql, params=None):
    """
    Pass in a buffer of one or more semicolon-terminated trino SQL statements and it
    will be parsed into individual statements for execution. If preprocessor is None,
    then the resulting SQL and bind parameters are used. If a preprocessor is needed,
    then it should be a callable taking two positional arguments and returning a 2-element tuple:
        pre_process(sql, parameters) -> (processed_sql, processed_parameters)
    Parameters:
        presto_conn (trino.dbapi.Connection) : Connection to presto
        sql (str) : Buffer of one or more semicolon-terminated SQL statements.
        params (Iterable, dict, None) : Parameters used in the SQL or None if no parameters
    Returns:
        list : Results of SQL statement execution.
    """
    # trino.Cursor.execute does not use parameters.
    # The sql_mogrify function will do any needed parameter substitution
    # and only returns the SQL with parameters formatted inline.
    presto_stmt = sql_mogrify(sql, params)
    presto_cur = _cursor(presto_conn)
    presto_cur = _execute(presto_cur, presto_stmt)
    results = _fetchall(presto_cur)
    if presto_cur.description is None:
        columns = []
    else:
        columns = [col[0] for col in presto_cur.description]

    return results, columns


def executescript(presto_conn, sqlscript, params=None, preprocessor=None):
    """
    Pass in a buffer of one or more semicolon-terminated trino SQL statements and it
    will be parsed into individual statements for execution. If preprocessor is None,
    then the resulting SQL and bind parameters are used. If a preprocessor is needed,
    then it should be a callable taking two positional arguments and returning a 2-element tuple:
        pre_process(sql, parameters) -> (processed_sql, processed_parameters)
    Parameters:
        presto_conn (trino.dbapi.Connection) : Connection to presto
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
        p_stmt = str(p_stmt).strip()
        if p_stmt:
            # A semicolon statement terminator is invalid in the Presto dbapi interface
            if p_stmt.endswith(";"):
                p_stmt = p_stmt[:-1]

            # This is typically for jinjasql templated sql
            if preprocessor and params:
                try:
                    stmt, s_params = preprocessor(p_stmt, params)
                # If a different preprocessor is used, we can't know what the exception type is.
                except Exception as e:
                    LOG.warning(
                        f"Preprocessor Error ({e.__class__.__name__}) : {str(e)}"
                        + os.linesep
                        + f"Statement template : {p_stmt}"
                        + os.linesep
                        + f"Parameters : {params}"
                    )
                    exc_type = e.__class__.__name__
                    raise PreprocessStatementError(f"{exc_type} :: {e}")
            else:
                stmt, s_params = p_stmt, params

            try:
                results, _ = execute(presto_conn, stmt, params=s_params)
            except Exception as e:
                exc_msg = (
                    f"Trino Query Error ({e.__class__.__name__}) : {str(e)} statement number {stmt_num}"
                    + os.linesep
                    + f"Statement: {stmt}"
                    + os.linesep
                    + f"Parameters: {s_params}"
                )
                LOG.warning(exc_msg)
                raise TrinoStatementExecError(exc_msg)

            all_results.extend(results)

    return all_results
