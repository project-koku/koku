#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database Extended Exceptions."""
import inspect
import json
import logging
import os
import re
import traceback

from django.db.utils import DatabaseError as DJDatabaseError
from psycopg2.errors import DatabaseError
from psycopg2.errors import DeadlockDetected
from sqlparse import parse as sql_parse
from sqlparse.sql import Comparison
from sqlparse.sql import Identifier
from sqlparse.sql import IdentifierList
from sqlparse.tokens import CTE
from sqlparse.tokens import DML


# import psycopg2
# from psycopg2.extras import RealDictCursor


LOG = logging.getLogger(__name__)


def get_driver_exception(db_exception):
    if isinstance(db_exception, DJDatabaseError):
        return db_exception.__cause__ or db_exception.__context__
    else:
        return db_exception


class ExtendedDBException(Exception):
    REGEXP = None

    def __init__(self, db_exception, query_limit=128):
        _db_exception = get_driver_exception(db_exception)
        if not isinstance(_db_exception, DatabaseError):
            raise TypeError(
                "This wrapper class only works on type <psycopg2.errors.DatabaseError> "
                + f"(Got {type(_db_exception).__name__})"
            )
        self.query_limit = query_limit
        self.ingest_exception(_db_exception)
        self.parse_exception()
        self.get_extended_info()

    def __str__(self):
        return f"EXCEPTION: {self.db_exception_type.__name__}{os.linesep}{os.linesep.join(str(a) for a in self.args)}"

    def __repr__(self):
        return str(self)

    def ingest_exception(self, db_exception):
        self.db_exception_type = type(db_exception)
        self.args = db_exception.args
        self.__traceback__ = db_exception.__traceback__
        self.cursor = getattr(db_exception, "cursor", None)
        self.query = self.cursor.query.decode("utf-8").strip() if self.cursor else ""
        self.diag = getattr(db_exception, "diag", None)
        self.pgcode = getattr(db_exception, "pgcode", None)
        self.pgerror = getattr(db_exception, "pgerror", None)
        if self.cursor and self.cursor.connection:
            self.db_backend_pid = self.cursor.connection.get_backend_pid()
        else:
            self.db_backend_pid = None

    def as_dict(self):
        return {
            "exception_type": self.db_exception_type,
            "message": str(self),
            "exception_code_file": self.exc_file,
            "exception_code_line_num": self.exc_line_num,
            "exception_code_line": self.exc_line,
            "koku_exception_code_file": self.koku_exc_file,
            "koku_exception_code_line_num": self.koku_exc_line_num,
            "koku_exception_code_line": self.koku_exc_line,
            "cursor_name": (self.cursor.name if self.cursor else "") or "",
            "query": self.query,
            "query_type": self.query_type,
            "query_tables": self.query_tables,
            "pgcode": self.pgcode,
            "pgerror": self.pgerror,
            "db_backend_pid": self.db_backend_pid,
            "traceback": self.formatted_tb,
        }

    def as_json(self):
        return json.dumps(self.as_dict(), default=str)

    def set_exception_frame_info(self, _frames):
        if _frames:
            _frame = _frames[-1]
            self.exc_line = _frame.line
            self.exc_line_num = _frame.lineno
            self.exc_file = _frame.filename
        else:
            self.exc_line = self.exc_line_num = self.exc_file = None

    def set_koku_exception_frame_info(self, _frames):
        if _frames:
            _koku_frame = None
            for _frame in _frames:
                if "koku" in _frame.filename:
                    _koku_frame = _frame
                else:
                    break
            if _koku_frame and _koku_frame.filename != self.exc_file and _koku_frame.lineno != self.exc_line_num:
                self.koku_exc_line = _frame.line
                self.koku_exc_line_num = _frame.lineno
                self.koku_exc_file = _frame.filename
            else:
                self.koku_exc_line = self.koku_exc_line_num = self.koku_exc_file = None
        else:
            self.koku_exc_line = self.koku_exc_line_num = self.koku_exc_file = None

    def get_tables_from_tokens(self, tokens, num_tokens, dml_type=None, seen_object=None, identifiers=None):  # noqa
        if seen_object is None:
            seen_object = set()
        if identifiers is None:
            identifiers = []

        ix = 0
        while ix < num_tokens:
            tok = tokens[ix]
            if tok.ttype in (CTE, DML):
                dml_type = tok.ttype
            elif isinstance(tok, Identifier):
                tok_name = tok.get_real_name()
                id_block = not bool(identifiers) or identifiers[-1].get_alias() != tok_name
                if tok_name not in seen_object and id_block:
                    identifiers.append(tok)
                    seen_object.add(tok_name)
                    if dml_type != CTE:
                        self.query_tables.append(tok_name)

            if dml_type == CTE and isinstance(tok, IdentifierList):
                allow_idlist = True
            else:
                allow_idlist = not isinstance(tok, IdentifierList)
            if tok.is_group and allow_idlist and not isinstance(tok, Comparison):
                sub_tokens = tok.tokens
                num_sub_tokens = len(sub_tokens)
                if num_sub_tokens > 0:
                    self.get_tables_from_tokens(
                        sub_tokens, num_sub_tokens, dml_type=dml_type, seen_object=seen_object, identifiers=identifiers
                    )

            ix += 1

    def parse_exception(self):
        _frames = traceback.extract_tb(self.__traceback__)
        self.set_exception_frame_info(_frames)
        self.set_koku_exception_frame_info(_frames)

        self.formatted_tb = traceback.format_tb(self.__traceback__)
        self.query_type = None
        self.query_tables = []
        if self.query:
            parsed_tokens = sql_parse(self.query)
            if parsed_tokens:
                self.query_type = parsed_tokens[0].get_type()
                self.get_tables_from_tokens(parsed_tokens, len(parsed_tokens))

    def get_extended_info(self):
        args_query = self.query[: self.query_limit] if self.query_limit else self.query
        self.args = (
            f"DB BACKEND PID: {self.db_backend_pid}",
            f"QUERY TYPE: {self.query_type or '<UNKNOWN>'}",
            f"QUERY TABLES: {self.query_tables or '<UNKNOWN>'}",
            f"QUERY: {args_query}",
        ) + self.args

    # def connect(self, application_name="ExtendedInfoGetter"):
    #     from koku.configurator import CONFIGURATOR

    #     if CONFIGURATOR.get_database_ca():
    #         ssl_opts = {"sslmode": "verify-full", "sslrootcert": CONFIGURATOR.get_database_ca_file()}
    #     else:
    #         ssl_opts = {"sslmode": "prefer"}

    #     return psycopg2.connect(
    #         host=CONFIGURATOR.get_database_host(),
    #         port=CONFIGURATOR.get_database_port(),
    #         user=CONFIGURATOR.get_database_user(),
    #         password=CONFIGURATOR.get_database_password(),
    #         dbname=CONFIGURATOR.get_database_name(),
    #         cursor_factory=RealDictCursor,
    #         **ssl_opts,
    #     )


class ExtendedDeadlockDetected(ExtendedDBException):
    REGEXP = re.compile(
        r"deadlock detected.*?\nDETAIL:\s*?"
        + r"Process (\d+).+? transaction (\d+).*?blocked by process (\d+).*?\n"
        + r"Process (\d+).+? transaction (\d+).*?blocked by process (\d+).*?\n",
        flags=re.DOTALL,
    )

    def parse_exception(self):
        super().parse_exception()

        res = self.REGEXP.findall(str(self))
        if res:
            identifiers = []
            for i in res[0]:
                try:
                    identifiers.append(int(i))
                except ValueError:
                    identifiers.append(i)

            self.process1, self.txaction1, self.blocker2, self.process2, self.txaction2, self.blocker1 = identifiers
        else:
            self.process1, self.txaction1, self.blocker2, self.process2, self.txaction2, self.blocker1 = None

    def get_extended_info(self):
        super().get_extended_info()

        # Commented-out because it would be nice to figure out how to successfully get the current log file
        # There's just not a super-pressing need for it currently.
        # try:
        #     with self.connect() as conn:
        #         with conn.cursor() as cur:
        #             cur.execute("select pg_current_logfile() as curr_log;")
        #             res = cur.fetchone()
        #             self.current_log_file = res["curr_log"] if res else None
        # except DatabaseError as e:
        #     LOG.warning(f"Error connecting to database for extended deadlock info: {str(e)}")
        #     self.current_log_file = "<Unknown> (DB connect error)"

        # self.args = (
        #     f"CURRENT DB LOG FILE: {self.current_log_file}",
        #     f"DEADLOCKED DATABASE PIDS: [{self.process1}, {self.process2}]",
        # ) + self.args

        self.args = (f"DEADLOCKED DATABASE PIDS: [{self.process1}, {self.process2}]",) + self.args

    def as_dict(self):
        data = super().as_dict()
        # data["current_db_log_file"] = self.current_log_file
        data["process1_pid"] = self.process1
        data["transxation1"] = self.txaction1
        data["process2_pid"] = self.process2
        data["transxation2"] = self.txaction2
        return data


__EXCEPTION_REGISTER = {_class.__name__ for _class in locals() if inspect.isclass(_class)}


def get_extended_exception_by_type(db_exception):
    _db_exception = get_driver_exception(db_exception)
    key = f"Extended{type(_db_exception).__name__}"
    if key in __EXCEPTION_REGISTER:
        return locals()[key](db_exception)
    else:
        return get_extended_exception_by_base_type(_db_exception)


def get_extended_exception_by_base_type(db_exception):
    _db_exception = get_driver_exception(db_exception)
    if isinstance(_db_exception, DeadlockDetected):
        return ExtendedDeadlockDetected(db_exception)
    else:
        return ExtendedDBException(db_exception)
