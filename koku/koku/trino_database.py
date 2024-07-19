import logging
import os
import re
import typing as t

import sqlparse
import trino
from trino.exceptions import TrinoQueryError
from trino.transaction import IsolationLevel

LOG = logging.getLogger(__name__)

POSITIONAL_VARS = re.compile("%s")
NAMED_VARS = re.compile(r"%(.+)s")
EOT = re.compile(r",\s*\)$")  # pylint: disable=anomalous-backslash-in-string


class TrinoStatementExecError(Exception):
    def __init__(
            self,
            statement: str,
            statement_number: int,
            sql_params: dict[str, t.Any],
            trino_error: t.Optional[TrinoQueryError] = None,
    ):
        self.statement = statement
        self.statement_number = statement_number
        self.sql_params = sql_params
        self._trino_error = trino_error

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"type={self.error_type}, "
            f"name={self.error_name}, "
            f"message={self.message}, "
            f"query_id={self.query_id})"
        )

    def __str__(self):
        return (
            f"Trino Query Error ({self._trino_error.__class__.__name__}) : "
            f"{self._trino_error} statement number {self.statement_number}{os.linesep}"
            f"Statement: {self.statement}{os.linesep}"
            f"Parameters: {self.sql_params}"
        )

    def __reduce__(self):
        return (self.__class__, (self.statement, self.statement_number, self.sql_params, self._trino_error))

    @property
    def error_code(self) -> t.Optional[int]:
        return self._trino_error.error_code

    @property
    def error_name(self) -> t.Optional[str]:
        return self._trino_error.error_name

    @property
    def error_type(self) -> t.Optional[str]:
        return self._trino_error.error_type

    @property
    def error_exception(self) -> t.Optional[str]:
        return self._trino_error.error_exception

    @property
    def failure_info(self) -> t.Optional[dict[str, t.Any]]:
        return self._trino_error.failure_info

    @property
    def message(self) -> str:
        return self._trino_error.message

    @property
    def query_id(self) -> t.Optional[str]:
        return self._trino_error.query_id


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
        "host": (connect_args.get("host") or os.environ.get("TRINO_HOST") or "trino"),
        "port": (connect_args.get("port") or os.environ.get("TRINO_PORT") or 8080),
        "user": (connect_args.get("user") or os.environ.get("TRINO_USER") or "admin"),
        "catalog": (connect_args.get("catalog") or os.environ.get("TRINO_DEFAULT_CATALOG") or "hive"),
        "isolation_level": (
                connect_args.get("isolation_level")
                or os.environ.get("TRINO_DEFAULT_ISOLATION_LEVEL")
                or IsolationLevel.AUTOCOMMIT
        ),
        "schema": connect_args["schema"],
        "legacy_primitive_types": connect_args.get("legacy_primitive_types", False),
        "max_attempts": 9,  # based on exponential backoff used in the trino lib, 9 max retries with take ~100 seconds
    }
    return trino.dbapi.connect(**trino_connect_args)


def executescript(trino_conn, sqlscript, *, params=None, preprocessor=None, trino_external_error_retries=3):
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
            # A semicolon statement terminator is invalid in the Trino dbapi interface
            p_stmt = p_stmt.removesuffix(";")
            # This is typically for jinjasql templated sql
            if preprocessor and params:
                stmt, s_params = preprocessor(p_stmt, params)
                LOG.debug(f"processed templated sql:\n\tstmt: {stmt}\n\ts_params: {s_params}")
            else:
                stmt, s_params = p_stmt, params
            if stmt == "":
                # When using if in jinja's we have to put the endif before
                # the semicolon otherwise sqlparse will will cut off the
                # the endif jinja tag. After the preprocessor is run
                # if the condition is false an empty line is returned.
                continue

            try:
                cur = trino_conn.cursor()
                cur.execute(stmt, params=s_params)
                results = cur.fetchall()
            except TrinoQueryError as trino_exc:
                if "NoSuchKey" in trino_exc.message and trino_external_error_retries > 0:
                    LOG.warning("TrinoExternalError Exception, retrying...")
                    return executescript(
                        trino_conn=trino_conn,
                        sqlscript=sqlscript,
                        params=params,
                        preprocessor=preprocessor,
                        trino_external_error_retries=trino_external_error_retries - 1,
                    )
                trino_statement_error = TrinoStatementExecError(
                    statement=stmt, statement_number=stmt_num, sql_params=s_params, trino_error=trino_exc
                )
                LOG.warning(f"{trino_statement_error!s}")
                raise trino_statement_error from trino_exc
            except Exception as exc:
                LOG.warning(str(exc))
                raise

            all_results.extend(results)

    return all_results
