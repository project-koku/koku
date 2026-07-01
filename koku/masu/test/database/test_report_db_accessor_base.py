#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportDBAccessorBase utility object."""
import os
from unittest.mock import MagicMock
from unittest.mock import patch

import psycopg2
from django.db import OperationalError
from psycopg2.errors import DeadlockDetected

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
