import functools
import logging
import os
import random
import re
import time
import typing as t

from django.db.utils import ProgrammingError as DjangoProgrammingError
from koku.reportdb_accessor import get_report_db_accessor
import sqlparse
from trino.exceptions import TrinoExternalError
from trino.exceptions import TrinoQueryError
from trino.transaction import IsolationLevel

from api.common import log_json
from koku import settings

LOG = logging.getLogger(__name__)

POSITIONAL_VARS = re.compile("%s")
NAMED_VARS = re.compile(r"%(.+)s")
EOT = re.compile(r",\s*\)$")  # pylint: disable=anomalous-backslash-in-string

########################################################
# Comments about moving from Trino to Postgres
# 1. The retry logic is not needed for Postgres. There are errors that happen dur to the separation of hive/trino/s3.
# 2. The isolation level is not needed for Postgres. It is always AUTOCOMMIT which is the default for postgres.
# 3. The exceptions defined in this file are not needed for Postgres. We can start with rleying on the Django (psycopg2) exceptions.
########################################################

class KokuError(Exception):
    ...


class KokuTrinoError(KokuError):
    """Base exception for our custom Trino errors"""

    def __init__(self, message, query_id=None, error_code=None):
        self.message = message
        self.query_id = query_id
        self.error_code = error_code

    def __str__(self):
        return f"{self.__class__.__name__}: {self.message}, Query ID: {self.query_id}, Error Code: {self.error_code}"


class TrinoStatementExecError(KokuTrinoError):
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


class TrinoNoSuchKeyError(KokuTrinoError):
    """NoSuchKey errors raised by Trino"""


class TrinoHiveMetastoreError(KokuTrinoError):
    """Hive Metastore errors raised by Trino"""


class TrinoQueryNotFoundError(KokuTrinoError):
    """Query not found (404) errors from Trino - typically temporary"""


def extract_context_from_sql_params(sql_params: dict[str, t.Any]) -> dict[str, t.Any]:
    ctx = {}
    if sql_params is None:
        return ctx
    if schema := sql_params.get("schema"):
        ctx["schema"] = schema
    if (start := sql_params.get("start")) or (start := sql_params.get("start_date")):
        ctx["start_date"] = start
    if (end := sql_params.get("end")) or (end := sql_params.get("end_date")):
        ctx["end_date"] = end
    if invoice_month := sql_params.get("invoice_month"):
        ctx["invoice_month"] = invoice_month
    if provider_uuid := sql_params.get("source_uuid"):
        ctx["provider_uuid"] = provider_uuid
    if cluster_id := sql_params.get("cluster_id"):
        ctx["cluster_id"] = cluster_id

    return ctx


def retry(
    original_callable: t.Callable = None,
    *,
    retries: int = settings.HIVE_PARTITION_DELETE_RETRIES,
    retry_on: type[Exception] | tuple[type[Exception], ...] = TrinoExternalError,
    max_wait: int = 30,
    log_message: t.Optional[str] = "Retrying...",
):
    """Decorator with the retry logic."""

    def _retry(callable: t.Callable):
        @functools.wraps(callable)
        def wrapper(*args, **kwargs):
            context = kwargs.get("context", extract_context_from_sql_params(kwargs.get("sql_params", {}))) or None
            for attempt in range(retries + 1):
                try:
                    LOG.debug(f"Attempt {attempt + 1} for {callable.__name__}")
                    return callable(*args, **kwargs)

                except retry_on as ex:
                    LOG.debug(f"Exception caught: {ex}")
                    if attempt < retries - 1:
                        LOG.warning(
                            log_json(
                                msg=f"{log_message} (attempt {attempt + 1})",
                                context=context,
                                exc_info=ex,
                            )
                        )
                        backoff = min(2**attempt, max_wait)
                        jitter = random.uniform(0, 1)
                        delay = backoff + jitter
                        LOG.debug(f"Sleeping for {delay} seconds before retrying")
                        time.sleep(delay)
                        continue

                    LOG.error(
                        log_json(
                            msg=f"Failed execution after {attempt + 1} attempts",
                            context=context,
                            exc_info=ex,
                        )
                    )
                    raise

        return wrapper

    if original_callable:
        return _retry(original_callable)

    return _retry


def connect(**connect_args):
    """
    Establish a databse connection. For ONPREM the connection is not via Trino, but via Django.
    Keyword Params:
        schema (str) : trino schema (required)
        host (str) : trino hostname (can set from environment)
        port (int) : trino port (can set from environment)
        user (str) : trino user (can set from environment)
        catalog (str) : trino catalog (can set from enviromment)
    Returns:
        Python DB-API 2.0 compatible connection object
    """
    trino_connect_args = {
        "host": (connect_args.get("host") or os.environ.get("TRINO_HOST") or "trino"),
        "port": (connect_args.get("port") or os.environ.get("TRINO_PORT") or 8080),
        "user": (connect_args.get("user") or os.environ.get("TRINO_USER") or "admin"),
        "catalog": (connect_args.get("catalog") or os.environ.get("TRINO_DEFAULT_CATALOG") or "hive"),
        "isolation_level": ( # I don't think this is really in use. I think it is always AUTOCOMMIT which is the default for postgres.
            connect_args.get("isolation_level")
            or os.environ.get("TRINO_DEFAULT_ISOLATION_LEVEL")
            or IsolationLevel.AUTOCOMMIT
        ),
        "schema": connect_args["schema"],
        "legacy_primitive_types": connect_args.get("legacy_primitive_types", False),
        "max_attempts": 9,  # based on exponential backoff used in the trino lib, 9 max retries with take ~100 seconds
    }
    return get_report_db_accessor().connect(**trino_connect_args)


@retry(retry_on=(TrinoNoSuchKeyError, TrinoHiveMetastoreError))
def executescript(trino_conn, sqlscript, *, params=None, preprocessor=None):
    """
    Pass in a buffer of one or more semicolon-terminated trino SQL statements and it
    will be parsed into individual statements for execution. If preprocessor is None,
    then the resulting SQL and bind parameters are used. If a preprocessor is needed,
    then it should be a callable taking two positional arguments and returning a 2-element tuple:
        pre_process(sql, parameters) -> (processed_sql, processed_parameters)
    Parameters:
        trino_conn : Python DB-API 2.0 compatible connection object
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
            except DjangoProgrammingError as e:
                # PostgreSQL raises "no results to fetch" for CREATE/DROP without RETURNING
                if "no results to fetch" in str(e):
                    results = []
                else:
                    raise
            except TrinoQueryError as trino_exc:
                exc_to_raise = TrinoStatementExecError(
                    statement=stmt, statement_number=stmt_num, sql_params=s_params, trino_error=trino_exc
                )
                if "NoSuchKey" in str(trino_exc):
                    exc_to_raise = TrinoNoSuchKeyError(
                        message=trino_exc.message,
                        query_id=trino_exc.query_id,
                        error_code=trino_exc.error_code,
                    )

                if trino_exc.error_name == "HIVE_METASTORE_ERROR":
                    exc_to_raise = TrinoHiveMetastoreError(
                        message=trino_exc.message,
                        query_id=trino_exc.query_id,
                        error_code=trino_exc.error_code,
                    )

                LOG.warning(f"{exc_to_raise!s}")
                raise exc_to_raise from trino_exc
            except Exception as exc:
                LOG.warning(str(exc))
                raise

            all_results.extend(results)

    return all_results
