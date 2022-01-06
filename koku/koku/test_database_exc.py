#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import json
import os

import psycopg2
from django.db import connection
from django.db import IntegrityError
from psycopg2.errors import DeadlockDetected
from psycopg2.errors import DivisionByZero
from sqlparse import parse as sql_parse

from . import database_exc as dbex
from api.iam.test.iam_test_case import IamTestCase
from koku.configurator import CONFIGURATOR


class TestDatabaseExc(IamTestCase):
    def _new_connection(self):
        raw_conn = connection.connection
        return psycopg2.connect(password=CONFIGURATOR.get_database_password(), **raw_conn.get_dsn_parameters())

    def test_real_exception(self):
        """Test a **real** exception from another connection to the DB."""

        with self._new_connection() as conn2:
            eexc = None
            sql = "select 1 / 0 from api_provider;"
            with conn2.cursor() as cur:
                try:
                    cur.execute(sql)
                except DivisionByZero as x:
                    eexc = dbex.get_extended_exception_by_type(x)

            self.assertEqual(type(eexc), dbex.ExtendedDBException)
            self.assertEqual(eexc.query, sql)
            self.assertEqual(DivisionByZero, eexc.db_exception_type)
            self.assertTrue(eexc.formatted_tb)
            self.assertTrue(eexc.query_tables)
            self.assertEqual(eexc.query_tables[0], "api_provider")
            self.assertGreater(eexc.db_backend_pid, 0)
            eedict = eexc.as_dict()
            self.assertEqual(type(eedict), dict)
            # Test json
            eedict_json = json.dumps(eedict, default=str)
            self.assertEqual(eexc.as_json(), eedict_json)

    def test_deadlock_exception(self):
        """Test deadlock exception message parsing."""
        ddexc = DeadlockDetected(
            "deadlock detected"
            + os.linesep
            + "DETAIL: Process 12  transaction 34  blocked by process 56"
            + os.linesep
            + "Process 56  transaction 78  blocked by process 12"
            + os.linesep
        )
        eexc = dbex.get_extended_exception_by_type(ddexc)

        self.assertEqual(type(eexc), dbex.ExtendedDeadlockDetected)
        self.assertEqual(DeadlockDetected, eexc.db_exception_type)
        self.assertEqual(sorted([eexc.process1, eexc.process2]), sorted([12, 56]))
        # self.assertTrue(hasattr(eexc, "current_log_file"))
        eedict = eexc.as_dict()
        self.assertEqual(type(eedict), dict)
        self.assertTrue({"process1_pid", "process2_pid"}.issubset(set(eedict)))

    def test_bad_exception(self):
        class BadException(Exception):
            pass

        exc = BadException("It's really bad!")
        with self.assertRaises(TypeError):
            _ = dbex.get_extended_exception_by_type(exc)

    def test_django_exception(self):
        dxc = IntegrityError("It's really bad!")
        dxc.__cause__ = DivisionByZero("Don't do it!")
        eexc = dbex.get_extended_exception_by_type(dxc)
        self.assertEqual(type(eexc), dbex.ExtendedDBException)

    def test_tables_from_complex_query(self):
        sql_buff = """
insert into eek (id, name, data)
select a.id, b.name, c.data
  from table_a a
  join table_b b
    on b.a_id = a.id
  left
  join table_c c
    on c.b_id = b.id;
"""
        expected_tables = ["eek", "table_a", "table_b", "table_c"]
        tokens = sql_parse(sql_buff)
        my_exc = dbex.ExtendedDBException(DivisionByZero("It's really bad!"))
        my_exc.query_tables = []
        my_exc.get_tables_from_tokens(tokens, len(tokens))
        self.assertEqual(my_exc.query_tables, expected_tables)

    def test_excpetion_subclass(self):
        """Test that extended exception can resolve correctly by base exception class."""

        class SubDD(DeadlockDetected):
            pass

        class SubDZ(DivisionByZero):
            pass

        ddexc = SubDD(
            "deadlock detected"
            + os.linesep
            + "DETAIL: Process 12  transaction 34  blocked by process 56"
            + os.linesep
            + "Process 56  transaction 78  blocked by process 12"
            + os.linesep
        )
        base_x = dbex.get_extended_exception_by_base_type(ddexc)
        x = dbex.get_extended_exception_by_type(ddexc)
        self.assertEqual(type(base_x), dbex.ExtendedDeadlockDetected)
        self.assertEqual(type(base_x), type(x))

        dzexc = SubDZ("eek")
        base_x = dbex.get_extended_exception_by_base_type(dzexc)
        x = dbex.get_extended_exception_by_type(dzexc)
        self.assertEqual(type(base_x), dbex.ExtendedDBException)
        self.assertEqual(type(base_x), type(x))
