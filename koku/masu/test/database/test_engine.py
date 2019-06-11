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

"""Test the SQLAlchemy enginer creation."""

from sqlalchemy import engine, pool

from masu.config import Config
from masu.database.engine import create_engine, _create_engine_kwargs
from tests import MasuTestCase

class DBEngineTest(MasuTestCase):
    """Test cases for the engine module."""

    def test_create_engine(self):
        """Test that a SQLAlchemy engine is created."""
        db_engine = create_engine()

        # expected_url = postgresql://kokuadmin:***@localhost:15432/test

        expected_url = Config.SQLALCHEMY_DATABASE_URI.split('@')
        start = expected_url[0].split(':')
        start = ':'.join(start[:-1] + ['***'])
        end = expected_url[1]
        expected_url = '@'.join([start] + [end])

        self.assertIsInstance(db_engine, engine.base.Engine)
        self.assertEqual(repr(db_engine.url), expected_url)
        self.assertIsInstance(db_engine.pool, pool.QueuePool)
        self.assertEqual(db_engine.pool.size(), Config.SQLALCHEMY_POOL_SIZE)

    def test_create_engine_kwargs(self):
        kwargs, cert_file = _create_engine_kwargs('dummy_cert')
        expected = {
            'client_encoding': 'utf8',
            'pool_size': Config.SQLALCHEMY_POOL_SIZE,
            'connect_args': {
                'sslmode': 'verify-full',
                'sslrootcert': cert_file
            }
        }
        self.assertEqual(expected, kwargs)
