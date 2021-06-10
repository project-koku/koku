#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the prometheus metrics."""
import logging
import random
from unittest import mock
from unittest.mock import Mock
from unittest.mock import patch

from django.db import OperationalError
from faker import Faker

from api.iam.test.iam_test_case import IamTestCase
from koku.metrics import collect_metrics
from koku.metrics import DatabaseStatus
from koku.metrics import REGISTRY

FAKE = Faker()


# noqa: W0212,E1101
class DatabaseStatusTest(IamTestCase):
    """Test DatabaseStatus object."""

    def test_db_is_connected(self):
        """Test that db is connected and logs at DEBUG level."""
        logging.disable(logging.NOTSET)
        with self.assertLogs(logger="koku.metrics", level=logging.DEBUG):
            DatabaseStatus().connection_check()

    @patch("koku.metrics.connection")
    def test_db_is_not_connected(self, mock_connection):
        """Test that db is not connected, log at ERROR level and counter increments."""
        mock_connection.cursor.side_effect = OperationalError("test exception")
        logging.disable(logging.NOTSET)
        before = REGISTRY.get_sample_value("db_connection_errors_total")
        self.assertIsNotNone(before)
        with self.assertLogs(logger="koku.metrics", level=logging.ERROR):
            DatabaseStatus().connection_check()
        after = REGISTRY.get_sample_value("db_connection_errors_total")
        self.assertIsNotNone(after)
        self.assertEqual(1, after - before)

    @patch("koku.metrics.push_to_gateway")
    @patch("koku.metrics.DatabaseStatus.collect")
    def test_celery_task(self, mock_collect, mock_push):
        """Test celery task to increment prometheus counter."""
        before = REGISTRY.get_sample_value("db_connection_errors_total")
        self.assertIsNotNone(before)
        with mock.patch("django.db.backends.utils.CursorWrapper") as mock_cursor:
            mock_cursor.side_effect = OperationalError("test exception")
            mock_collect.return_value = []
            task = collect_metrics.s().apply()
            self.assertTrue(task.successful())
        after = REGISTRY.get_sample_value("db_connection_errors_total")
        self.assertIsNotNone(after)
        self.assertEqual(1, after - before)

    @patch("koku.metrics.push_to_gateway", side_effect=OSError)
    @patch("koku.metrics.DatabaseStatus.collect")
    def test_celery_task_no_pushgateway(self, _, __):
        """Test that we handle connection issues gracefully."""
        logging.disable(logging.NOTSET)
        with self.assertLogs(logger="koku.metrics", level=logging.ERROR):
            collect_metrics.s().apply()

    @patch("koku.metrics.DatabaseStatus.query", return_value=True)
    def test_schema_size(self, mock_status):
        """Test schema_size()."""
        dbs = DatabaseStatus()
        result = dbs.schema_size()
        assert mock_status.called
        self.assertTrue(result)

    @patch("koku.metrics.PGSQL_GAUGE.labels")
    @patch("koku.metrics.DatabaseStatus.query", return_value=[{"schema": "foo", "size": 10}])
    def test_collect(self, _, mock_gauge):
        """Test collect()."""
        dbs = DatabaseStatus()
        dbs.collect()
        self.assertTrue(mock_gauge.called)

    @patch("koku.metrics.push_to_gateway")
    @patch("koku.metrics.DatabaseStatus.query", return_value=[{"schema": "foo", "size": 10}])
    def test_collect_metrics(self, _, mock_push):
        """Test collect_metrics."""
        collect_metrics()
        self.assertTrue(mock_push.called)

    @patch("koku.metrics.PGSQL_GAUGE.labels")
    @patch("koku.metrics.DatabaseStatus.query", return_value=[{"schema": None, "size": None}])
    def test_collect_bad_schema_size(self, _, mock_gauge):
        """Test collect with None data types."""
        dbs = DatabaseStatus()
        dbs.collect()
        self.assertFalse(mock_gauge.called)

    @patch("time.sleep", return_value=None)  # make this test go 6 seconds faster :)
    def test_query_exception(self, patched_sleep):
        """Test _query() when an exception is thrown."""
        logging.disable(logging.NOTSET)
        with mock.patch("django.db.backends.utils.CursorWrapper") as mock_cursor:
            mock_cursor = mock_cursor.return_value.__enter__.return_value
            mock_cursor.execute.side_effect = OperationalError("test exception")
            test_query = "SELECT count(*) from now()"
            dbs = DatabaseStatus()
            with self.assertLogs(logger="koku.metrics", level=logging.WARNING):
                result = dbs.query(test_query, "test_query")
            self.assertFalse(result)

    @patch("koku.metrics.connection")
    def test_query_return_empty(self, mock_connection):
        """Test that empty query returns [] and logs info."""
        # Mocked up objects:
        #   connection.cursor().fetchall()
        #   connection.cursor().description
        mock_ctx = Mock(return_value=Mock(description=[("schema",), ("size",)], fetchall=[("chicken", 2)]))
        mock_connection.cursor = Mock(return_value=Mock(__enter__=mock_ctx, __exit__=mock_ctx))
        logging.disable(logging.NOTSET)
        dbs = DatabaseStatus()
        with self.assertLogs(logger="koku.metrics", level=logging.INFO):
            result = dbs.schema_size()
        self.assertFalse(result)

    @patch("koku.metrics.connection")
    def test_schema_size_valid(self, mock_connection):
        """Test that schema_size() parses rows correctly."""
        fake_rows = [(FAKE.word(), FAKE.pyint()) for _ in range(0, random.randint(2, 20))]

        # Mocked up objects:
        #   connection.cursor().fetchall()
        #   connection.cursor().description
        mock_ctx = Mock(return_value=Mock(description=[("schema",), ("size",)], fetchall=Mock(return_value=fake_rows)))
        mock_connection.cursor = Mock(return_value=Mock(__enter__=mock_ctx, __exit__=mock_ctx))

        expected = [dict(zip(["schema", "size"], row)) for row in fake_rows if len(row) == 2]
        dbs = DatabaseStatus()
        result = dbs.schema_size()
        self.assertEqual(result, expected)

    @patch("koku.metrics.connection")
    def test_schema_size_null(self, mock_connection):
        """Test that schema_size() parses rows with null values correctly."""
        fake_rows = [
            (random.choice([FAKE.word(), "", None]), random.choice([FAKE.pyint(), "", None]))
            for _ in range(0, random.randint(2, 20))
        ]

        # Mocked up objects:
        #   connection.cursor().fetchall()
        #   connection.cursor().description
        mock_ctx = Mock(return_value=Mock(description=[("schema",), ("size",)], fetchall=Mock(return_value=fake_rows)))
        mock_connection.cursor = Mock(return_value=Mock(__enter__=mock_ctx, __exit__=mock_ctx))

        expected = [dict(zip(["schema", "size"], row)) for row in fake_rows if len(row) == 2]
        dbs = DatabaseStatus()
        result = dbs.schema_size()
        self.assertEqual(result, expected)
