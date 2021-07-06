import logging
import os
import re
from decimal import Decimal

import prestodb
import sqlparse
from prestodb.exceptions import PrestoQueryError
from prestodb.transaction import IsolationLevel


LOG = logging.getLogger(__name__)

POSITIONAL_VARS = re.compile("%s")
NAMED_VARS = re.compile(r"%(.+)s")
EOT = re.compile(r",\s*\)$")  # pylint: disable=anomalous-backslash-in-string


class PreprocessStatementError(Exception):
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
    Establish a prestodb connection.
    Keyword Params:
        schema (str) : prestodb schema (required)
        host (str) : prestodb hostname (can set from environment)
        port (int) : prestodb port (can set from environment)
        user (str) : prestodb user (can set from environment)
        catalog (str) : prestodb catalog (can set from enviromment)
    Returns:
        prestodb.dbapi.Connection : connection to prestodb if successful
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
    conn = prestodb.dbapi.connect(**presto_connect_args)
    return conn


def _fetchall(presto_cur):
    """
    Wrapper around the prestodb.dbapi.Cursor.fetchall() method
    Params:
        presto_cur (presto.dbapi.Cursor) : Presto cursor that has already called the execute method
    Returns:
        list : Results of cursor execution and results fetch
    """
    return presto_cur.fetchall()


def _cursor(presto_conn):
    """
    Wrapper around the prestodb.dbapi.Connection.cursor() method
    Params:
        presto_conn (prestodb.dbapi.Connection) Active presto connection
    Returns:
        prestodb.dbapi.Cursor : Cursor for the connection
    """
    return presto_conn.cursor()


def _execute(presto_cur, presto_stmt):
    """
    Wrapper around the prestodb.dbapi.Cursor.execute() method
    Params:
        presto_cur (prestodb.dbapi.Cursor) : presto connection cursor
        presto_stmt (str) : presto SQL statement
    Returns:
        prestodb.dbapi.Cursor : Cursor after execute method called
    """
    presto_cur.execute(presto_stmt)
    return presto_cur


def execute(presto_conn, sql, params=None):
    """
    Pass in a buffer of one or more semicolon-terminated prestodb SQL statements and it
    will be parsed into individual statements for execution. If preprocessor is None,
    then the resulting SQL and bind parameters are used. If a preprocessor is needed,
    then it should be a callable taking two positional arguments and returning a 2-element tuple:
        pre_process(sql, parameters) -> (processed_sql, processed_parameters)
    Parameters:
        presto_conn (prestodb.dbapi.Connection) : Connection to presto
        sql (str) : Buffer of one or more semicolon-terminated SQL statements.
        params (Iterable, dict, None) : Parameters used in the SQL or None if no parameters
    Returns:
        list : Results of SQL statement execution.
    """
    # prestodb.Cursor.execute does not use parameters.
    # The sql_mogrify function will do any needed parameter substitution
    # and only returns the SQL with parameters formatted inline.
    presto_stmt = sql_mogrify(sql, params)
    presto_cur = _cursor(presto_conn)
    try:
        LOG.debug(f"Executing PRESTO SQL: {presto_stmt}")
        presto_cur = _execute(presto_cur, presto_stmt)
        results = _fetchall(presto_cur)
    except PrestoQueryError as e:
        LOG.error(f"Presto Query Error : {str(e)}{os.linesep}{presto_stmt}")
        raise e

    return results


def executescript(presto_conn, sqlscript, params=None, preprocessor=None):
    """
        Pass in a buffer of one or more semicolon-terminated prestodb SQL statements and it
        will be parsed into individual statements for execution. If preprocessor is None,
        then the resulting SQL and bind parameters are used. If a preprocessor is needed,
        then it should be a callable taking two positional arguments and returning a 2-element tuple:
            pre_process(sql, parameters) -> (processed_sql, processed_parameters)
        Parameters:
            presto_conn (prestodb.dbapi.Connection) : Connection to presto
            sqlscript (str) : Buffer of one or more semicolon-terminated SQL statements.
            params (Iterable, dict, None) : Parameters used in the SQL or None if no parameters
            preprocessor (Callable, None) : Callable taking two args and returning a 2-element tuple
                                            or None if no preprocessor is needed
        Returns:
            list : Results of each successful SQL statement executed.
        """
    results = []
    stmt_count = 0
    # sqlparse.split() should be a safer means to split a sql script into discrete statements
    for p_stmt in sqlparse.split(sqlscript):
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
                    LOG.error(f"Preprocessor Error ({e.__class__.__name__}) : {str(e)}")
                    LOG.error(f"Statement template : {p_stmt}")
                    LOG.error(f"Parameters : {params}")
                    exc_type = e.__class__.__name__
                    raise PreprocessStatementError(f"{exc_type} :: {e}")
            else:
                stmt, s_params = p_stmt, params

            results.extend(execute(presto_conn, stmt, params=s_params))
    return results
