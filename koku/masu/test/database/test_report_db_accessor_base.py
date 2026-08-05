#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportDBAccessorBase utility object."""
import ast
import inspect
import os
import pathlib
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

import psycopg2
from django.db import OperationalError
from psycopg2.errors import DeadlockDetected

import masu
from koku.cache import build_trino_schema_exists_key
from koku.cache import build_trino_table_exists_key
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.test import MasuTestCase


def _make_deadlock_operational_error():
    """Build a Django OperationalError wrapping a real psycopg2 DeadlockDetected.

    This mirrors what Django's postgres backend does in production: the psycopg2
    driver exception is wrapped in django.db.utils.OperationalError with __cause__
    set to the original driver exception.
    """
    # Mirrors real Postgres formatting: the second "Process" line of a multi-line
    # DETAIL is indented to align under the first. A prior version of this mock
    # omitted the indentation, which masked a bug where ExtendedDeadlockDetected's
    # regex failed to parse the (very common) indented, real-world message shape.
    deadlock = DeadlockDetected(
        "deadlock detected"
        + os.linesep
        + "DETAIL:  Process 12 waits for ShareLock on transaction 34; blocked by process 56."
        + os.linesep
        + "        Process 56 waits for ShareLock on transaction 78; blocked by process 12."
        + os.linesep
    )
    django_exc = OperationalError(str(deadlock))
    django_exc.__cause__ = deadlock
    return django_exc


def _make_generic_operational_error():
    """Build a Django OperationalError wrapping a non-deadlock psycopg2 error (e.g. lost connection)."""
    driver_exc = psycopg2.OperationalError("could not connect to server")
    django_exc = OperationalError(str(driver_exc))
    django_exc.__cause__ = driver_exc
    return django_exc


class ReportDBAccessorBaseTest(MasuTestCase):
    """Test Cases for the ReportDBAccessorBase object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = ReportDBAccessorBase(schema=cls.schema)

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_schema_exists_cache_value_in_cache(self, trino_mock):
        with patch(
            "masu.database.report_db_accessor_base.get_value_from_cache",
            return_value=True,
        ):
            self.assertTrue(self.accessor.schema_exists_trino())
            trino_mock.assert_not_called()

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_schema_exists_cache_value_not_in_cache(self, trino_mock):
        trino_mock.return_value = True
        key = build_trino_schema_exists_key(self.schema)
        with patch("masu.database.report_db_accessor_base.set_value_in_cache") as mock_cache_set:
            self.assertTrue(self.accessor.schema_exists_trino())
            mock_cache_set.assert_called_with(key, True)

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_schema_exists_cache_value_not_in_cache_not_exists(self, trino_mock):
        trino_mock.return_value = False
        key = build_trino_schema_exists_key(self.schema)
        with patch("masu.database.report_db_accessor_base.set_value_in_cache") as mock_cache_set:
            self.assertFalse(self.accessor.schema_exists_trino())
            mock_cache_set.assert_called_with(key, False)

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_table_exists_cache_value_in_cache(self, trino_mock):
        with patch(
            "masu.database.report_db_accessor_base.get_value_from_cache",
            return_value=True,
        ):
            self.assertTrue(self.accessor.table_exists_trino("table"))
            trino_mock.assert_not_called()

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_table_exists_cache_value_not_in_cache(self, trino_mock):
        trino_mock.return_value = True
        table = "table"
        key = build_trino_table_exists_key(self.schema, table)
        with patch("masu.database.report_db_accessor_base.set_value_in_cache") as mock_cache_set:
            self.assertTrue(self.accessor.table_exists_trino(table))
            mock_cache_set.assert_called_with(key, True)

    @patch.object(ReportDBAccessorBase, "_execute_trino_raw_sql_query")
    def test_table_exists_cache_value_not_in_cache_not_exists(self, trino_mock):
        trino_mock.return_value = False
        table = "table"
        key = build_trino_table_exists_key(self.schema, table)
        with patch("masu.database.report_db_accessor_base.set_value_in_cache") as mock_cache_set:
            self.assertFalse(self.accessor.table_exists_trino(table))
            mock_cache_set.assert_called_with(key, False)


class ReportDBAccessorBaseDeadlockRetryTest(MasuTestCase):
    """Test that raw SQL execution retries transparently on Postgres deadlocks.

    Postgres deadlocks are expected, transient conditions in a multi-writer system:
    the deadlock detector always rolls one transaction back cleanly, so retrying is
    both safe (no partial state to clean up under the current autocommit-per-statement
    execution model) and the standard recommended way to handle them. These tests pin
    down that `_execute_raw_sql_query` treats a deadlock as retryable but does not
    retry other, unrelated `OperationalError`s (e.g. lost connections).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.accessor = ReportDBAccessorBase(schema=cls.schema)

    def _mock_cursor_cm(self, cursor_mock):
        """Build a mock for `connection.cursor()` that behaves like a context manager."""
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cursor_mock
        cursor_cm.__exit__.return_value = False
        return cursor_cm

    @patch("masu.database.report_db_accessor_base.time.sleep")
    @patch("masu.database.report_db_accessor_base.connection")
    def test_execute_raw_sql_query_retries_and_recovers_from_deadlock(self, mock_connection, mock_sleep):
        """A single deadlock should be retried transparently and ultimately succeed."""
        cursor_mock = MagicMock()
        cursor_mock.execute.side_effect = [_make_deadlock_operational_error(), None]
        cursor_mock.rowcount = 5
        mock_connection.cursor.return_value = self._mock_cursor_cm(cursor_mock)

        result = self.accessor._execute_raw_sql_query("rates_to_usage", "DELETE FROM rates_to_usage")

        self.assertIsNone(result)
        self.assertEqual(cursor_mock.execute.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("koku.trino_database.LOG")
    @patch("masu.database.report_db_accessor_base.time.sleep")
    @patch("masu.database.report_db_accessor_base.connection")
    def test_execute_raw_sql_query_retry_log_includes_deadlock_detail(self, mock_connection, mock_sleep, mock_log):
        """The retry-warning log line must carry the deadlock's own diagnostic detail.

        Previously this line only logged a generic message plus a raw (unserializable)
        exception object under an `exc_info` key, and derived its `context` from a
        `sql_params` kwarg that `_execute_raw_sql_query` never actually received (it was
        named `bind_params`), so the line carried no query/table/PID detail at all --
        exactly the gap raised in PR #6162 review (comment on this file's `@retry` call).
        """
        cursor_mock = MagicMock()
        cursor_mock.execute.side_effect = [_make_deadlock_operational_error(), None]
        cursor_mock.rowcount = 5
        mock_connection.cursor.return_value = self._mock_cursor_cm(cursor_mock)

        self.accessor._execute_raw_sql_query("rates_to_usage", "DELETE FROM rates_to_usage")

        mock_log.warning.assert_called_once()
        (logged,), _ = mock_log.warning.call_args
        self.assertEqual(logged["message"], "Deadlock detected, retrying statement (attempt 1)")
        self.assertNotIn("exc_info", logged)
        detail = logged["exception_detail"]
        self.assertEqual(detail["process1_pid"], 12)
        self.assertEqual(detail["process2_pid"], 56)
        self.assertIn("DEADLOCKED DATABASE PIDS: [12, 56]", detail["message"])

    @patch("masu.database.report_db_accessor_base.time.sleep")
    @patch("masu.database.report_db_accessor_base.connection")
    def test_execute_raw_sql_query_raises_after_exhausting_deadlock_retries(self, mock_connection, mock_sleep):
        """A persistent deadlock should be retried a bounded number of times, then raised."""

        def _always_deadlock(*args, **kwargs):
            raise _make_deadlock_operational_error()

        cursor_mock = MagicMock()
        cursor_mock.execute.side_effect = _always_deadlock
        mock_connection.cursor.return_value = self._mock_cursor_cm(cursor_mock)

        from koku.database_exc import ExtendedDeadlockDetected

        with self.assertRaises(ExtendedDeadlockDetected):
            self.accessor._execute_raw_sql_query("rates_to_usage", "DELETE FROM rates_to_usage")

        self.assertGreater(cursor_mock.execute.call_count, 1)
        mock_sleep.assert_called()

    @patch("masu.database.report_db_accessor_base.time.sleep")
    @patch("masu.database.report_db_accessor_base.connection")
    def test_execute_raw_sql_query_does_not_retry_non_deadlock_operational_error(self, mock_connection, mock_sleep):
        """A non-deadlock OperationalError (e.g. lost connection) must fail fast, not retry."""
        cursor_mock = MagicMock()
        cursor_mock.execute.side_effect = _make_generic_operational_error()
        mock_connection.cursor.return_value = self._mock_cursor_cm(cursor_mock)

        from koku.database_exc import ExtendedDBException

        with self.assertRaises(ExtendedDBException):
            self.accessor._execute_raw_sql_query("rates_to_usage", "DELETE FROM rates_to_usage")

        self.assertEqual(cursor_mock.execute.call_count, 1)
        mock_sleep.assert_not_called()


class RawSqlRetryIdempotencyGuardTest(TestCase):
    """Guards the safety argument backing retry-on-deadlock in `_execute_raw_sql_query`.

    That retry is only safe because every current call site executes the raw SQL
    as an independent, autocommitted unit of work (Django's default AUTOCOMMIT=True;
    no surrounding `transaction.atomic()`). Retrying is the standard Postgres-
    recommended way to handle a deadlock in that shape, but if a future change wraps
    a `_execute_raw_sql_query`/`_prepare_and_execute_raw_sql_query` call inside
    `transaction.atomic()` alongside other statements, blindly retrying just the raw
    SQL call on deadlock could silently replay only part of a larger unit of work
    (raised in PR #6162 review). This is a static trip-wire, not a full guarantee:
    it fails loudly if one of these two methods is called from inside a
    `transaction.atomic()` block/decorator in one of these files, so a human
    re-verifies the safety argument rather than it silently rotting.

    Note this deliberately does NOT flag every `transaction.atomic()` usage in these
    files -- only ones that actually wrap a call to the two retried methods. PR #6232
    (COST-7995) added an unrelated `transaction.atomic()` block to
    `ocp_report_db_accessor.populate_markup_cost()` that takes a Postgres advisory
    lock around a plain Django ORM `.update()`; it never calls either retried method,
    so it carries none of the risk this guard exists for and must not trip it.
    """

    # All current subclasses of ReportDBAccessorBase (the only source of
    # `_execute_raw_sql_query`/`_prepare_and_execute_raw_sql_query` calls in the codebase).
    ACCESSOR_FILES = (
        "database/report_db_accessor_base.py",
        "database/aws_report_db_accessor.py",
        "database/azure_report_db_accessor.py",
        "database/gcp_report_db_accessor.py",
        "database/ocp_report_db_accessor.py",
    )

    RETRIED_RAW_SQL_METHODS = ("_execute_raw_sql_query", "_prepare_and_execute_raw_sql_query")

    @staticmethod
    def _is_transaction_atomic_attr(node):
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "atomic"
            and isinstance(node.value, ast.Name)
            and node.value.id == "transaction"
        )

    @classmethod
    def _is_transaction_atomic_usage(cls, node):
        """True for `transaction.atomic` used as a `with` context manager or decorator.

        Deliberately AST-based (not a text/substring search): this method's own
        docstring mentions "transaction.atomic()" in prose, which would otherwise
        be a false positive for a naive `"transaction.atomic" in content` check.
        """
        if isinstance(node, ast.Call):
            node = node.func
        return cls._is_transaction_atomic_attr(node)

    @classmethod
    def _contains_retried_raw_sql_call(cls, node):
        """True if `node`'s subtree calls `_execute_raw_sql_query`/`_prepare_and_execute_raw_sql_query`."""
        return any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in cls.RETRIED_RAW_SQL_METHODS
            for n in ast.walk(node)
        )

    @classmethod
    def _offending_atomic_usages(cls, source: str) -> list:
        """Return the `transaction.atomic` AST nodes in `source` that wrap a retried raw-SQL call."""
        tree = ast.parse(source)
        offending = []
        for node in ast.walk(tree):
            if isinstance(node, ast.With):
                atomic_items = [
                    item.context_expr for item in node.items if cls._is_transaction_atomic_usage(item.context_expr)
                ]
                if atomic_items and cls._contains_retried_raw_sql_call(node):
                    offending.extend(atomic_items)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                atomic_decorators = [deco for deco in node.decorator_list if cls._is_transaction_atomic_usage(deco)]
                if atomic_decorators and cls._contains_retried_raw_sql_call(node):
                    offending.extend(atomic_decorators)
        return offending

    def test_no_atomic_block_in_raw_sql_accessor_files(self):
        masu_dir = pathlib.Path(inspect.getfile(masu)).resolve().parent
        for relative_path in self.ACCESSOR_FILES:
            path = masu_dir / relative_path
            offending = self._offending_atomic_usages(path.read_text())
            self.assertFalse(
                offending,
                f"masu/{relative_path} now calls _execute_raw_sql_query/_prepare_and_execute_raw_sql_query "
                "from inside a transaction.atomic() block or decorator. Re-verify this is intentional -- "
                "the deadlock-retry safety argument in "
                "ReportDBAccessorBase._execute_raw_sql_query's docstring assumes these calls are "
                "always independently autocommitted.",
            )

    def test_atomic_block_without_raw_sql_call_is_not_offending(self):
        """PR #6232's advisory-lock pattern (atomic block, no retried call inside) must not trip the guard."""
        source = """
from django.db import connection, transaction

class Accessor:
    def populate_markup_cost(self, markup, start_date, end_date, cluster_id):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [cluster_id])
            SomeModel.objects.filter(cluster_id=cluster_id).update(markup=markup)
"""
        self.assertEqual(self._offending_atomic_usages(source), [])

    def test_atomic_block_wrapping_raw_sql_call_is_offending(self):
        """A retried raw-SQL call nested inside `transaction.atomic()` must trip the guard."""
        source = """
from django.db import transaction

class Accessor:
    def delete_then_insert(self, table, sql, sql_params):
        with transaction.atomic():
            self._execute_raw_sql_query(table, sql, sql_params=sql_params)
"""
        self.assertEqual(len(self._offending_atomic_usages(source)), 1)

    def test_atomic_decorator_wrapping_raw_sql_call_is_offending(self):
        """A retried raw-SQL call inside a `@transaction.atomic()`-decorated method must trip the guard."""
        source = """
from django.db import transaction

class Accessor:
    @transaction.atomic()
    def delete_then_insert(self, table, sql, sql_params):
        self._prepare_and_execute_raw_sql_query(table, sql, sql_params)
"""
        self.assertEqual(len(self._offending_atomic_usages(source)), 1)
