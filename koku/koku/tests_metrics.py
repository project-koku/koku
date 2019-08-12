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
from unittest import mock
from unittest.mock import patch

from django.db import connection, OperationalError

from api.iam.test.iam_test_case import IamTestCase
from koku.metrics import DatabaseStatus


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

    def test_query(self):
        """Test _query()."""
        test_query = 'SELECT count(*) from now()'
        expected = [{'count': 1}]
        dbs = DatabaseStatus()
        result = dbs.query(test_query)
        self.assertEqual(result, expected)

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
