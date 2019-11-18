#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the prometheus metrics."""
import logging
import random
from datetime import datetime
from unittest import mock
from unittest.mock import Mock, patch

from django.db import OperationalError
from faker import Faker

from api.iam.test.iam_test_case import IamTestCase
from koku.metrics import DatabaseStatus

FAKE = Faker()


# noqa: W0212,E1101
# pylint: disable=no-member,protected-access
class DatabaseStatusTest(IamTestCase):
    """Test DatabaseStatus object."""

    @patch('koku.metrics.DatabaseStatus.query', return_value=True)
    def test_schema_size(self, mock_status):
        """Test schema_size()."""
        dbs = DatabaseStatus()
        result = dbs.schema_size()
        assert mock_status.called
        self.assertTrue(result)

    @patch('koku.metrics.PGSQL_GAUGE.labels')
    @patch('koku.metrics.DatabaseStatus.query', return_value=[{'schema': 'foo',
                                                               'size': 10}])
    def test_collect(self, _, mock_gauge):
        """Test collect()."""
        dbs = DatabaseStatus()
        dbs.collect()
        self.assertTrue(mock_gauge.called)

    def test_query_cache(self):
        """Test that query() returns a cached response when available."""
        dbs = DatabaseStatus()
        dbs._last_result = 1
        dbs._last_query = datetime.now()
        result = dbs.query('SELECT count(*) from now()')
        self.assertEqual(result, 1)

    def test_query_exception(self):
        """Test _query() when an exception is thrown."""
        logging.disable(0)
        with mock.patch('django.db.backends.utils.CursorWrapper') as mock_cursor:
            mock_cursor = mock_cursor.return_value.__enter__.return_value
            mock_cursor.execute.side_effect = OperationalError('test exception')
            test_query = 'SELECT count(*) from now()'
            dbs = DatabaseStatus()
            with self.assertLogs(level=logging.WARNING):
                dbs.query(test_query)

    @patch('koku.metrics.connection')
    def test_schema_size_valid(self, mock_connection):
        """ Test that schema_size() parses rows correctly."""
        fake_rows = [(FAKE.word(), FAKE.pyint())
                     for _ in range(0, random.randint(2, 20))]

        # Mocked up objects:
        #   connection.cursor().fetchall()
        #   connection.cursor().description
        mock_ctx = Mock(return_value=Mock(description=[('schema',), ('size',)],
                                          fetchall=Mock(return_value=fake_rows)))
        mock_connection.cursor = Mock(return_value=Mock(__enter__=mock_ctx,
                                                        __exit__=mock_ctx))

        expected = [dict(zip(['schema', 'size'], row)) for row in fake_rows if len(row) == 2]
        dbs = DatabaseStatus()
        result = dbs.schema_size()
        self.assertEqual(result, expected)

    @patch('koku.metrics.connection')
    def test_schema_size_null(self, mock_connection):
        """ Test that schema_size() parses rows with null values correctly."""
        fake_rows = [(random.choice([FAKE.word(), '', None]),
                      random.choice([FAKE.pyint(), '', None]))
                     for _ in range(0, random.randint(2, 20))]

        # Mocked up objects:
        #   connection.cursor().fetchall()
        #   connection.cursor().description
        mock_ctx = Mock(return_value=Mock(description=[('schema',), ('size',)],
                                          fetchall=Mock(return_value=fake_rows)))
        mock_connection.cursor = Mock(return_value=Mock(__enter__=mock_ctx,
                                                        __exit__=mock_ctx))

        expected = [dict(zip(['schema', 'size'], row)) for row in fake_rows if len(row) == 2]
        dbs = DatabaseStatus()
        result = dbs.schema_size()
        self.assertEqual(result, expected)
